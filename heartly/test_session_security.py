import time

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from heartly.middleware import (
    SESSION_ACTIVITY_KEY,
    SESSION_CREATED_KEY,
)


User = get_user_model()


@override_settings(
    HEARTLY_ENFORCE_ADULT_IDENTITY=False,
    HEARTLY_REQUIRE_VERIFIED_EMAIL=False,
    HEARTLY_SESSION_IDLE_TIMEOUT_SECONDS=60,
    HEARTLY_SESSION_ABSOLUTE_TIMEOUT_SECONDS=300,
    HEARTLY_SESSION_ACTIVITY_UPDATE_SECONDS=1,
)
class SessionSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="session-security",
            email="session-security@example.com",
            password="StrongPass123!",
        )
        self.client.force_login(self.user)

    def set_session_times(self, *, created_at, activity_at):
        session = self.client.session
        session[SESSION_CREATED_KEY] = created_at
        session[SESSION_ACTIVITY_KEY] = activity_at
        session.save()

    def test_authenticated_response_seeds_bounds_and_is_private(self):
        response = self.client.get(reverse("settings"))
        session = self.client.session

        self.assertEqual(response.status_code, 200)
        self.assertIn(SESSION_CREATED_KEY, session)
        self.assertIn(SESSION_ACTIVITY_KEY, session)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(
            response["Referrer-Policy"],
            "strict-origin-when-cross-origin",
        )
        self.assertIn("camera=(self)", response["Permissions-Policy"])

    def test_idle_session_is_logged_out_and_redirected(self):
        now = int(time.time())
        self.set_session_times(
            created_at=now - 100,
            activity_at=now - 61,
        )

        response = self.client.get(reverse("settings"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.url.startswith(reverse("account_login"))
        )
        self.assertIn("session=expired", response.url)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_absolute_session_limit_is_enforced(self):
        now = int(time.time())
        self.set_session_times(
            created_at=now - 301,
            activity_at=now,
        )

        response = self.client.get(reverse("settings"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("session=expired", response.url)

    def test_expired_write_returns_private_json_401(self):
        now = int(time.time())
        self.set_session_times(
            created_at=now - 301,
            activity_at=now,
        )

        response = self.client.post(
            reverse("send_email_code"),
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["ok"])
        self.assertIn("login_url", response.json())
        self.assertIn("no-store", response["Cache-Control"])
