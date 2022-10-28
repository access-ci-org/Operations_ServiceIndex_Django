#from django.db import models
#import time
import logging
from django.contrib.auth.models import User
from allauth.account.signals import user_logged_in
from django.db.models.signals import pre_save
from django.dispatch import receiver, Signal
from allauth.socialaccount.providers.cilogon import provider
from allauth.socialaccount.providers.oauth2.client import OAuth2Error

#@receiver(pre_save, sender=User)
@receiver(user_logged_in)
def set_username(request, user, **kwargs):
    subject = user.socialaccount_set.filter(provider='cilogon')[0].extra_data['sub']
    username, domain = subject.split('@')[:2]
    if domain != 'access-ci.org':
        raise OAuth2Error("ACCESS CI Identity must be used or linked")
    else:
        user.username = username
        user.save()
