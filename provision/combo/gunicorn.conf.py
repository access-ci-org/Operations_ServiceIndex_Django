proc_name = 'django'
user = 'appuser'
group = 'appuser'
daemon = True
workers = 3
# IP:PORT
bind = ':8080'
pidfile = '/soft/serviceindex-1.0/var/django.pid'
accesslog = '/soft/serviceindex-1.0/var/django.log'
access_log_format = '%({x-forwarded-for}i)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'
errorlog = '/soft/serviceindex-1.0/var/django.error.log'
loglevel = 'debug'
