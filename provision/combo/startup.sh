#!/bin/bash

#service nginx start
#service django start
/usr/sbin/sshd -D &
/etc/init.d/nginx start &
/etc/init.d/django start &
while true; do sleep 1000; done
