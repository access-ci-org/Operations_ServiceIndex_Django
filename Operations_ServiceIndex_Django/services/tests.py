from types import SimpleNamespace

from allauth import app_settings as allauth_app_settings
from allauth.account.adapter import get_adapter as get_account_adapter
from allauth.socialaccount.adapter import get_adapter as get_socialaccount_adapter
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase
from django.urls import NoReverseMatch, resolve, reverse


class SignupPolicyTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/")
        self.request.user = AnonymousUser()
        self.request.session = {}

    def test_installed_allauth_supports_social_account_only(self):
        self.assertTrue(hasattr(allauth_app_settings, "SOCIALACCOUNT_ONLY"))

    def test_allauth_is_social_account_only(self):
        self.assertTrue(allauth_app_settings.SOCIALACCOUNT_ONLY)

    def test_local_signup_route_is_not_registered(self):
        with self.assertRaises(NoReverseMatch):
            reverse("account_signup")

    def test_local_signup_policy_is_closed(self):
        self.assertFalse(
            get_account_adapter(self.request).is_open_for_signup(self.request)
        )

    def test_cilogon_social_signup_policy_remains_open(self):
        sociallogin = SimpleNamespace(account=SimpleNamespace(provider="cilogon"))
        self.assertTrue(
            get_socialaccount_adapter(self.request).is_open_for_signup(
                self.request, sociallogin
            )
        )

    def test_other_social_signup_policies_are_closed(self):
        sociallogin = SimpleNamespace(account=SimpleNamespace(provider="other-provider"))
        self.assertFalse(
            get_socialaccount_adapter(self.request).is_open_for_signup(
                self.request, sociallogin
            )
        )

    def test_cilogon_login_route_remains_available(self):
        match = resolve(reverse("cilogon_login"))
        self.assertEqual(match.url_name, "cilogon_login")

    def test_django_admin_login_route_remains_available(self):
        match = resolve(reverse("admin:login"))
        self.assertEqual(match.url_name, "login")
