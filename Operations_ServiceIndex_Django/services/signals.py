#from django.db import models
#import time
from django.contrib.auth.models import User
from django.dispatch import receiver, Signal
from allauth.account.signals import user_logged_in, user_logged_out
from allauth.account.utils import sync_user_email_addresses, setup_user_email
from allauth.socialaccount.providers.cilogon import provider
from allauth.socialaccount.providers.oauth2.client import OAuth2Error
from allauth.socialaccount.signals import pre_social_login

import logging
logger = logging.getLogger(__name__)

@receiver(user_logged_in)
def set_username(request, user, **kwargs):
    try:
        sociallogin = user.socialaccount_set.filter(provider='cilogon')[0]
    except:
        raise OAuth2Error('ACCESS CI Identity required but not found')
        
    subject = sociallogin.extra_data.get('sub', '')
    username, domain = subject.split('@')[:2]
    if not username or domain != 'access-ci.org':
        raise OAuth2Error('ACCESS CI Identity was not used, linked, or was missing a username')

    user.username = username
    user.save()
    remote_ip = request.META.get('HTTP_X_FORWARDED_FOR')
    if not remote_ip:
        remote_ip = request.META.get('REMOTE_ADDR')
    msg = '{} logged in as {} from {}'.format(subject, request.user.username, remote_ip)
    logger.info(msg)

@receiver(user_logged_out)
def logout_log(request, user, **kwargs):
    msg = '{} logged out'.format(request.user.username)
    logger.info(msg)

@receiver(pre_social_login)
def connect_existing_user(request, sociallogin, **kwargs):
    if sociallogin.is_existing:
        return
    
    try:
        email = sociallogin.email_addresses[0]
    except:
        raise OAuth2Error('ACCESS CI Identity required email is missing')

    try:    # username is unique
        existing_user = User.objects.get(email=email)
    except: # Let socialaccount handle creation
        return

    sociallogin.connect(request, existing_user)
    setup_user_email(request, existing_user, [])
    msg = 'login as email {} connected to {}'.format(email, existing_user.username)
    logger.info(msg)
