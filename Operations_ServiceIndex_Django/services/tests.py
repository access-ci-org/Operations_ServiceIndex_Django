import base64
from types import SimpleNamespace

from allauth import app_settings as allauth_app_settings
from allauth.account.adapter import get_adapter as get_account_adapter
from allauth.socialaccount.adapter import get_adapter as get_socialaccount_adapter
from django.contrib.auth.models import AnonymousUser, Group, User
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import NoReverseMatch, resolve, reverse
from rest_framework.test import APIClient


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
        sociallogin = SimpleNamespace(
            account=SimpleNamespace(provider="other-provider")
        )
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


class ApiHostsAuthenticationTests(TestCase):
    password = "test-password"

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("services:api_hosts")
        self.viewers = Group.objects.create(name="viewers")
        self.editors = Group.objects.create(name="editors")

    def basic_auth(self, username, password=None):
        credentials = "{}:{}".format(username, password or self.password)
        token = base64.b64encode(credentials.encode()).decode()
        return "Basic {}".format(token)

    def create_user(self, username, group=None, is_active=True):
        user = User.objects.create_user(
            username=username,
            password=self.password,
            is_active=is_active,
        )
        if group is not None:
            user.groups.add(group)
        return user

    def test_missing_credentials_returns_unauthorized(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 401)
        self.assertTrue(response["WWW-Authenticate"].startswith("Basic"))

    def test_invalid_credentials_returns_unauthorized(self):
        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=self.basic_auth("unknown", "wrong-password"),
        )

        self.assertEqual(response.status_code, 401)

    def test_viewer_credentials_return_existing_response_schema(self):
        user = self.create_user("api-viewer", self.viewers)

        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=self.basic_auth(user.username),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status_code": "200", "results": []})

    def test_editor_credentials_are_authorized(self):
        user = self.create_user("api-editor", self.editors)

        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=self.basic_auth(user.username),
        )

        self.assertEqual(response.status_code, 200)

    def test_authenticated_user_without_group_is_forbidden(self):
        user = self.create_user("api-user")

        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=self.basic_auth(user.username),
        )

        self.assertEqual(response.status_code, 403)

    def test_inactive_user_is_unauthorized(self):
        user = self.create_user("inactive-api-user", self.viewers, is_active=False)

        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=self.basic_auth(user.username),
        )

        self.assertEqual(response.status_code, 401)

    def test_non_get_request_is_not_allowed(self):
        user = self.create_user("api-method-test", self.viewers)

        response = self.client.post(
            self.url,
            HTTP_AUTHORIZATION=self.basic_auth(user.username),
        )

        self.assertEqual(response.status_code, 405)
