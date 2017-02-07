#!/bin/bash

python setup.py install

function create_service() {
        echo "Creating service $1"
        touch /etc/systemd/system/$1.service
        chmod 664 /etc/systemd/system/$1.service
        cat << SERVICE > /etc/systemd/system/$1.service
[Unit]
Description=$1
After=network.target redis.service mariadb.service

[Service]
ExecStart=$2
Type=simple

[Install]
WantedBy=default.target
SERVICE
}

function create_uwsgi_service() {
        echo "Creating service $1"
        touch /etc/systemd/system/$1.service
        chmod 664 /etc/systemd/system/$1.service
        cat << SERVICE > /etc/systemd/system/$1.service
[Unit]
Description=$1
After=network.target redis.service mariadb.service

[Service]
ExecStart=/usr/sbin/uwsgi --ini $2
RuntimeDirectory=uwsgi
Restart=always
KillSignal=SIGQUIT
Type=notify
StandardError=syslog
NotifyAccess=all


[Install]
WantedBy=default.target
SERVICE
}


create_service s8 "/usr/bin/python $(pwd)/s8.py"
create_service a8 "/usr/bin/python $(pwd)/a8.py"
create_service p8 "/usr/bin/python $(pwd)/p8.py"
create_uwsgi_service w8 "$(pwd)/w8.ini"
