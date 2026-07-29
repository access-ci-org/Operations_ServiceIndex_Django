"""Authentication policy adapters for django-allauth."""

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class ClosedLocalSignupAdapter(DefaultAccountAdapter):
    """Disallow public creation of local username/password accounts."""

    def is_open_for_signup(self, request):
        return False


class CILogonSignupAdapter(DefaultSocialAccountAdapter):
    """Allow account creation only after authentication by CILogon."""

    def is_open_for_signup(self, request, sociallogin):
        return sociallogin.account.provider == "cilogon"
