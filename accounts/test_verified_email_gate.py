from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from profiles.models import Profile


User = get_user_model()


def years_ago(years):
    today = date.today()

    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(
            year=today.year - years,
            month=2,
            day=28,
        )


@override_settings(
    HEARTLY_REQUIRE_VERIFIED_EMAIL=True
)
class PostLoginVerificationGateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="login-gate-user",
            email="login-gate@example.com",
            password="StrongPass123!",
            full_name="Login Gate User",
            gender="male",
            interested_in="female",
            date_of_birth=years_ago(25),
        )
        self.profile = Profile.objects.get(user=self.user)
        self.profile.display_name = "Login Gate User"
        self.profile.age = self.user.age
        self.profile.gender = Profile.GENDER_MAN
        self.profile.interested_in = (
            Profile.INTERESTED_IN_WOMEN
        )
        self.profile.email_verified = False
        self.profile.save()
        self.client.force_login(self.user)

    @patch(
        "accounts.views._sync_profile_email_verification",
        return_value=False,
    )
    def test_unverified_user_is_sent_to_account_settings(
        self,
        _sync,
    ):
        response = self.client.get(
            reverse("post_login_redirect")
        )

        self.assertRedirects(
            response,
            reverse("settings_account"),
            fetch_redirect_response=False,
        )

    @patch(
        "accounts.views._sync_profile_email_verification",
        return_value=True,
    )
    def test_verified_user_continues_to_discover(
        self,
        _sync,
    ):
        response = self.client.get(
            reverse("post_login_redirect")
        )

        self.assertRedirects(
            response,
            reverse("matches:discover"),
            fetch_redirect_response=False,
        )
