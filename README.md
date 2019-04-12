Combination of scripts written by https://github.com/ableev/Zabbix-in-Telegram and the fork.
Requires an user on Zabbix who can consult issues (required for downloading images)


Setup:

0. pip install matrix_client
1. Create a user on the matrix-server for the zabbix_matrix bot.
2. Create rooms for users and add users (who will be receive zabbix-alerts). 
3. Accept invite from the zabbix_matrix user by each users. Note down the room id (!xxxxxx@xxxx.xx)
4. Clone the script in the alert_scripts folder of zabbix (on debian this is /usr/lib/zabbix/alert_scripts)
5. cp config.py.example config.py
6. edit config.py.example - add zabbix server accounts info (login and pass).
7. In zabbix: go  Administration/ Media type menu and add script as send-script. Add the following parameters:
- {ALERT.SENDTO}
- {ALERT.SUBJECT}
- {ALERT.MESSAGE}
8. Configure the new media type for the user that will receive the alerts: go to Administration / Users, click the user and go to the tab Media. Add the media type Matrix and include the room ID in SendTo


for testing, you can exec script manualy:

  ./matrix_send_message.py 'matrix_room_id' 'zabbix subject' 'zabbix event body text'
