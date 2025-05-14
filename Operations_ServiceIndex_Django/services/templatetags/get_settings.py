from django import template
from django.conf import settings

register = template.Library()

@register.simple_tag
def settings_value(name):
    return getattr(settings, name, "")

@register.filter
def can_admin_users(user):
    return (user.is_superuser or
            user.has_perm('auth.add_user') or
            user.groups.filter(name='account-admins').exists())