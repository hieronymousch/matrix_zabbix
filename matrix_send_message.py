#!/usr/bin/env python
# coding: utf-8

import sys
import os
import time
import random
import string
import requests
import json
import re
import stat
import hashlib
import subprocess
from os.path import dirname
import config as conf
from matrix_client.client import MatrixClient
from matrix_client.api import MatrixRequestError
import config as conf

class Cache:
    def __init__(self, database):
        self.database = database

    def create_db(self, database):
        pass

def markdown_fix(message, offset, emoji=False):
    offset = int(offset)
    if emoji:  # https://github.com/ableev/Zabbix-in-Telegram/issues/152
        offset -= 2
    message = "\n".join(message)
    message = message[:offset] + message[offset+1:]
    message = message.split("\n")
    return message


class ZabbixWeb:
    def __init__(self, server, username, password):
        self.debug = False
        self.server = server
        self.username = username
        self.password = password
        self.proxies = {}
        self.verify = True
        self.cookie = None
        self.basic_auth_user = None
        self.basic_auth_pass = None
        self.tmp_dir = None

    def login(self):
        if not self.verify:
            requests.packages.urllib3.disable_warnings()

        data_api = {"name": self.username, "password": self.password, "enter": "Sign in"}
        answer = requests.post(self.server + "/", data=data_api, proxies=self.proxies, verify=self.verify,
                               auth=requests.auth.HTTPBasicAuth(self.basic_auth_user, self.basic_auth_pass))
        cookie = answer.cookies
        if len(answer.history) > 1 and answer.history[0].status_code == 302:
            print_message("probably the server in your config file has not full URL (for example "
                          "'{0}' instead of '{1}')".format(self.server, self.server + "/zabbix"))
        if not cookie:
            print_message("authorization has failed, url: {0}".format(self.server + "/"))
            cookie = None

        self.cookie = cookie

    def graph_get(self, itemid, period, title, width, height, version=3):
        file_img = self.tmp_dir + "/{0}.png".format("".join(itemid))

        title = requests.utils.quote(title)

        colors = {
            0: "00CC00",
            1: "CC0000",
            2: "0000CC",
            3: "CCCC00",
            4: "00CCCC",
            5: "CC00CC",
        }

        drawtype = 5
        if len(itemid) > 1:
            drawtype = 2

        zbx_img_url_itemids = []
        for i in range(0, len(itemid)):
            itemid_url = "&items[{0}][itemid]={1}&items[{0}][sortorder]={0}&" \
                         "items[{0}][drawtype]={3}&items[{0}][color]={2}".format(i, itemid[i], colors[i], drawtype)
            zbx_img_url_itemids.append(itemid_url)

        zbx_img_url = self.server + "/chart3.php?"
        if version < 4:
            zbx_img_url += "period={0}".format(period)
        else:
            zbx_img_url += "from=now-{0}&to=now".format(period)
        zbx_img_url += "&name={0}&width={1}&height={2}&graphtype=0&legend=1".format(title, width, height)
        zbx_img_url += "".join(zbx_img_url_itemids)

        if self.debug:
            print_message(zbx_img_url)
        answer = requests.get(zbx_img_url, cookies=self.cookie, proxies=self.proxies, verify=self.verify,
                              auth=requests.auth.HTTPBasicAuth(self.basic_auth_user, self.basic_auth_pass))
        status_code = answer.status_code
        if status_code == 404:
            print_message("can't get image from '{0}'".format(zbx_img_url))
            return False
        res_img = answer.content
        file_bwrite(file_img, res_img)
        return file_img

    def api_test(self):
        headers = {'Content-type': 'application/json'}
        api_data = json.dumps({"jsonrpc": "2.0", "method": "user.login", "params":
                              {"user": self.username, "password": self.password}, "id": 1})
        api_url = self.server + "/api_jsonrpc.php"
        api = requests.post(api_url, data=api_data, proxies=self.proxies, headers=headers)
        return api.text


def print_message(message):
    message = str(message) + "\n"
    filename = sys.argv[0].split("/")[-1]
    sys.stderr.write(filename + ": " + message)


def list_cut(elements, symbols_limit):
    symbols_count = symbols_count_now = 0
    elements_new = []
    element_last_list = []
    for e in elements:
        symbols_count_now = symbols_count + len(e)
        if symbols_count_now > symbols_limit:
            limit_idx = symbols_limit - symbols_count
            e_list = list(e)
            for idx, ee in enumerate(e_list):
                if idx < limit_idx:
                    element_last_list.append(ee)
                else:
                    break
            break
        else:
            symbols_count = symbols_count_now + 1
            elements_new.append(e)
    if symbols_count_now < symbols_limit:
        return elements, False
    else:
        element_last = "".join(element_last_list)
        elements_new.append(element_last)
        return elements_new, True


def file_write(filename, text):
    with open(filename, "w") as fd:
        fd.write(str(text))
    return True


def file_bwrite(filename, data):
    with open(filename, "wb") as fd:
        fd.write(data)
    return True


def file_read(filename):
    with open(filename, "r") as fd:
        text = fd.readlines()
    return text


def file_append(filename, text):
    with open(filename, "a") as fd:
        fd.write(str(text))
    return True


def external_image_get(url, tmp_dir, timeout=6):
    image_hash = hashlib.md5()
    image_hash.update(url.encode())
    file_img = tmp_dir + "/external_{0}.png".format(image_hash.hexdigest())
    try:
        answer = requests.get(url, timeout=timeout, allow_redirects=True)
    except requests.exceptions.ReadTimeout as ex:
        print_message("Can't get external image from '{0}': timeout".format(url))
        return False
    status_code = answer.status_code
    if status_code == 404:
        print_message("Can't get external image from '{0}': HTTP 404 error".format(url))
        return False
    answer_image = answer.content
    file_bwrite(file_img, answer_image)
    return file_img


def age2sec(age_str):
    age_sec = 0
    age_regex = "([0-9]+d)?\s?([0-9]+h)?\s?([0-9]+m)?"
    age_pattern = re.compile(age_regex)
    intervals = age_pattern.match(age_str).groups()
    for i in intervals:
        if i:
            metric = i[-1]
            if metric == "d":
                age_sec += int(i[0:-1])*86400
            if metric == "h":
                age_sec += int(i[0:-1])*3600
            if metric == "m":
                age_sec += int(i[0:-1])*60
    return age_sec


def main():

    tmp_dir = conf.zbx_matrix_tmp_dir
    if tmp_dir == "/tmp/" + conf.zbx_tg_prefix:
        print_message("WARNING: it is strongly recommended to change `zbx_tg_tmp_dir` variable in config!!!")
        print_message("https://github.com/ableev/Zabbix-in-Telegram/wiki/Change-zbx_tg_tmp_dir-in-settings")

    tmp_cookie = tmp_dir + "/cookie.py.txt"
    tmp_uids = tmp_dir + "/uids.txt"
    tmp_need_update = False  # do we need to update cache file with uids or not

    rnd = random.randint(0, 999)
    ts = time.time()
    hash_ts = str(ts) + "." + str(rnd)

    log_file = conf.log_path

    args = sys.argv
	
    settings = {
        "zbxtg_itemid": "0",  # itemid for graph
        "zbxtg_title": None,  # title for graph
        "zbxtg_image_period": None,
        "zbxtg_image_age": "3600",
        "zbxtg_image_width": "900",
        "zbxtg_image_height": "200",
        "tg_method_image": False,  # if True - default send images, False - send text
        "is_debug": False,
        "is_channel": False,
        "disable_web_page_preview": False,
        "location": None,  # address
        "lat": 0,  # latitude
        "lon": 0,  # longitude
        "is_single_message": False,
        "markdown": False,
        "html": False,
        "signature": None,
        "signature_disable": False,
        "graph_buttons": False,
        "extimg": None,
        "to": None,
        "to_group": None,
        "forked": False,
    }

    settings_description = {
        "itemid": {"name": "zbxtg_itemid", "type": "list", "help": "script will attach a graph with that itemid (could be multiple)", "url": "Graphs"},
        "title": {"name": "zbxtg_title", "type": "str", "help": "title for attached graph", "url": "Graphs"},
        "graphs_period": {"name": "zbxtg_image_period", "type": "int", "help": "graph period", "url": "Graphs"},
        "graphs_age": {"name": "zbxtg_image_age", "type": "str", "help": "graph period as age", "url": "Graphs"},
        "graphs_width": {"name": "zbxtg_image_width", "type": "int", "help": "graph width", "url": "Graphs"},
        "graphs_height": {"name": "zbxtg_image_height", "type": "int", "help": "graph height", "url": "Graphs"},
        "graphs": {"name": "tg_method_image", "type": "bool", "help": "enables graph sending", "url": "Graphs"},
        "chat": {"name": "tg_chat", "type": "bool", "help": "deprecated, don't use it, see 'group'", "url": "How-to-send-message-to-the-group-chat"},
        "group": {"name": "tg_group", "type": "bool", "help": "sends message to a group", "url": "How-to-send-message-to-the-group-chat"},
        "debug": {"name": "is_debug", "type": "bool", "help": "enables 'debug'", "url": "How-to-test-script-in-command-line"},
        "channel": {"name": "is_channel", "type": "bool", "help": "sends message to a channel", "url": "Channel-support"},
        "disable_web_page_preview": {"name": "disable_web_page_preview", "type": "bool", "help": "disable web page preview", "url": "Disable-web-page-preview"},
        "location": {"name": "location", "type": "str", "help": "address of location", "url": "Location"},
        "lat": {"name": "lat", "type": "str", "help": "specify latitude (and lon too!)", "url": "Location"},
        "lon": {"name": "lon", "type": "str", "help": "specify longitude (and lat too!)", "url": "Location"},
        "single_message": {"name": "is_single_message", "type": "bool", "help": "do not split message and graph", "url": "Why-am-I-getting-two-messages-instead-of-one"},
        "markdown": {"name": "markdown", "type": "bool", "help": "markdown support", "url": "Markdown-and-HTML"},
        "html": {"name": "html", "type": "bool", "help": "markdown support", "url": "Markdown-and-HTML"},
        "signature": {"name": "signature", "type": "str","help": "bot's signature", "url": "Bot-signature"},
        "signature_disable": {"name": "signature_disable", "type": "bool","help": "enables/disables bot's signature", "url": "Bot-signature"},
        "graph_buttons": {"name": "graph_buttons", "type": "bool","help": "activates buttons under graph, could be using in ZbxTgDaemon",                          "url": "Interactive-bot"},
        "external_image": {"name": "extimg", "type": "str","help": "should be url; attaches external image from different source","url": "External-image-as-graph"},
        "to": {"name": "to", "type": "str", "help": "rewrite zabbix username, use that instead of arguments","url": "Custom-to-and-to_group"},
        "to_group": {"name": "to_group", "type": "str","help": "rewrite zabbix username, use that instead of arguments", "url": "Custom-to-and-to_group"},"forked": {"name": "forked", "type": "bool", "help": "internal variable, do not use it. Ever.", "url": ""},
    }

    if len(args) < 4:
        do_not_exit = False
        if "--features" in args:
            print(("List of available settings, see {0}/Settings\n---".format(url_wiki_base)))
            for sett, proprt in list(settings_description.items()):
                print(("{0}: {1}\ndoc: {2}/{3}\n--".format(sett, proprt["help"], url_wiki_base, proprt["url"])))

        elif "--show-settings" in args:
            do_not_exit = True
            print_message("Settings: " + str(json.dumps(settings, indent=2)))

        else:
            print(("Hi. You should provide at least three arguments.\n"
                   "zbxtg.py [TO] [SUBJECT] [BODY]\n\n"
                  "1. Read main page and/or wiki: {0} + {1}\n"
                  "2. Public Telegram group (discussion): {2}\n"
                  "3. Public Telegram channel: {3}\n"
                  "4. Try dev branch for test purposes (new features, etc): {0}/tree/dev"
                  .format(url_github, url_wiki_base, url_tg_group, url_tg_channel)))
        if not do_not_exit:
            sys.exit(0)


    zbx_to = args[1]
    zbx_subject = args[2]
    zbx_body = args[3]

    zbx = ZabbixWeb(server=conf.zbx_server, username=conf.zbx_api_user,
                    password=conf.zbx_api_pass)
    client = MatrixClient(conf.server)

    token=None
    try:
        token = client.login_with_password(username=conf.username, password=conf.password)
    except MatrixRequestError as e:
        print(e)
        if e.code == 403:
            print_message("Bad username or password.")
            sys.exit(4)
        else:
            print_message("Check your sever details are correct.")
            sys.exit(2)
    except MissingSchema as e:
        print_message("Bad URL format.")
        print(e)
        sys.exit(3)
    except:
        print_message("ERROR (unknown) login_with_password()!")
        sys.exit(5)

    room = None
    try:
        room = client.join_room(zbx_to)
    except MatrixRequestError as e:
        print(e)
        if e.code == 400:
            print_message("Room ID/Alias in the wrong format")
            sys.exit(11)
        else:
            print_message("Couldn't find room.")
            sys.exit(12)
    except:
        print_message("ERROR (unknown) join_room()!")
        sys.exit(13)

    zbx.tmp_dir = tmp_dir

    # workaround for Zabbix 4.x
    zbx_version = 3

    try:
        zbx_version = conf.zbx_server_version
    except:
        pass

#    if conf.proxy_to_zbx:
#        zbx.proxies = {
#            "http": "http://{0}/".format(conf.proxy_to_zbx),
#            "https": "https://{0}/".format(conf.proxy_to_zbx)
#        }

    # https://github.com/ableev/Zabbix-in-Telegram/issues/55
    try:
        if conf.zbx_basic_auth:
            zbx.basic_auth_user = conf.zbx_basic_auth_user
            zbx.basic_auth_pass = conf.zbx_basic_auth_pass
    except:
        pass

    try:
        zbx_api_verify = conf.zbx_api_verify
        zbx.verify = zbx_api_verify
    except:
        pass

    zbxtg_body = (zbx_subject + "\n" + zbx_body).splitlines()
    zbxtg_body_text = []
## seems redundant but necessary to avoid errors of using these variables before declaration... shouldn't happen
    tg_method_image = bool(settings["tg_method_image"])
    disable_web_page_preview = bool(settings["disable_web_page_preview"])
    is_single_message = bool(settings["is_single_message"])
   
    for line in zbxtg_body:
        if line.find(conf.zbx_tg_prefix) > -1:
            setting = re.split("[\s:=]+", line, maxsplit=1)
            key = setting[0].replace(conf.zbx_tg_prefix + ";", "")
            if key not in settings_description:
               # if "--debug" in args:
               room.send_text(str("[ERROR] There is no '{0}' method, use --features to get help".format(key)))
               # continue
            if settings_description[key]["type"] == "list":
                value = setting[1].split(",")
            elif len(setting) > 1 and len(setting[1]) > 0:
                value = setting[1]
            elif settings_description[key]["type"] == "bool":
                value = True
            else:
                value = settings[settings_description[key]["name"]]
            if key in settings_description:
                settings[settings_description[key]["name"]] = value
            if key == "graphs" and  value is True:
               tg_method_image  = True
        else:
            zbxtg_body_text.append(line)

    

    if conf.DEBUG:
        is_debug = True
        zbx.debug = True
        log_file = tmp_dir + ".debug." + hash_ts + ".log"
        print_message(log_file)

    if not os.path.isdir(tmp_dir):
        if is_debug:
            print_message("Tmp dir doesn't exist, creating new one...")
        try:
            os.makedirs(tmp_dir)
            os.chmod(tmp_dir, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        except:
            tmp_dir = "/tmp"
        if is_debug:
            print_message("Using {0} as a temporary dir".format(tmp_dir))

    done_all_work_in_the_fork = False
    # issue75

    if done_all_work_in_the_fork:
        sys.exit(0)

  
    # replace text with emojis
    internal_using_emoji = False  # I hate that, but... https://github.com/ableev/Zabbix-in-Telegram/issues/152
    if hasattr(conf, "emoji_map"):
        zbxtg_body_text_emoji_support = []
        for l in zbxtg_body_text:
            l_new = l
            for k, v in list(conf.emoji_map.items()):
                l_new = l_new.replace("{{" + k + "}}", v)
            zbxtg_body_text_emoji_support.append(l_new)
        if len("".join(zbxtg_body_text)) - len("".join(zbxtg_body_text_emoji_support)):
            internal_using_emoji = True
        zbxtg_body_text = zbxtg_body_text_emoji_support 

    if not is_single_message and tg_method_image is False:
        text="""%(zbx_subject)s 
        %(zbx_body)s
        """%{"zbx_subject":zbx_subject, "zbx_body":zbx_body}
        room.send_text(text)


    if settings["zbxtg_image_age"]:
        age_sec = age2sec(settings["zbxtg_image_age"])
        if age_sec > 0 and age_sec > 3600:
            settings["zbxtg_image_period"] = age_sec

    message_id = 0
    if tg_method_image is True:
        zbx.login()
        room.send_text(settings["zbxtg_title"] + "\n" + str(zbxtg_body_text[0])) 
        if not zbx.cookie:
            text_warn = "Login to Zabbix web UI has failed (web url, user or password are incorrect), "\
                        "unable to send graphs check manually"
            room.send_text([text_warn])
            print_message(text_warn)
        else:
            if not settings["extimg"]:
                zbxtg_file_img = zbx.graph_get(settings["zbxtg_itemid"], settings["zbxtg_image_period"],
                                               settings["zbxtg_title"], settings["zbxtg_image_width"],
                                               settings["zbxtg_image_height"], version=zbx_version)
            else:
                zbxtg_file_img = external_image_get(settings["extimg"], tmp_dir=zbx.tmp_dir)
            zbxtg_body_text, is_modified = list_cut(zbxtg_body_text, 200)
            if not zbxtg_file_img:
                text_warn = "Can't get graph image, check script manually, see logs, or disable graphs"
                room.send_text([text_warn])
                print_message(text_warn)
            else:
                if not is_single_message:
                    zbxtg_body_text = ""
                else:
                    if is_modified:
                        text_warn = "probably you will see MEDIA_CAPTION_TOO_LONG error, "\
                                    "the message has been cut to 200 symbols, "\
                                    "https://github.com/ableev/Zabbix-in-Telegram/issues/9"\
                                    "#issuecomment-166895044"
                        print_message(text_warn)
                in_file = open(zbxtg_file_img, "rb")
                uploaddata = in_file.read() # if you only wanted to read 512 bytes, do .read(512)
                in_file.close()
				
                response = client.upload(uploaddata,"image/png")
                room.send_image(str(response),zbxtg_file_img)
                os.remove(zbxtg_file_img)

    if "--show-settings" in args:
        print_message("Settings: " + str(json.dumps(settings, indent=2)))

if __name__ == "__main__":
    main()
