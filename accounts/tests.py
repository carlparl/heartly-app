from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.forms import CustomSignupForm
from profiles.models import Profile


User = get_user_model()


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)
class AccountsRoutesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="StrongPass123!",
        )
        self.client.force_login(self.user)

    def test_settings_home_loads(self):
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 200)

    def test_settings_account_loads(self):
        response = self.client.get(reverse("settings_account"))
        self.assertEqual(response.status_code, 200)

    def test_settings_privacy_redirects_to_settings_home(self):
        response = self.client.get(reverse("settings_privacy"))
        self.assertRedirects(
            response,
            reverse("settings"),
            fetch_redirect_response=False,
        )

    def test_notifications_settings_redirects_to_settings_home(self):
        response = self.client.get(reverse("notifications_home"))
        self.assertRedirects(
            response,
            reverse("settings"),
            fetch_redirect_response=False,
        )

    def test_settings_help_redirects_to_settings_home(self):
        response = self.client.get(reverse("settings_help"))
        self.assertRedirects(
            response,
            reverse("settings"),
            fetch_redirect_response=False,
        )

    def test_settings_about_redirects_to_settings_home(self):
        response = self.client.get(reverse("settings_about"))
        self.assertRedirects(
            response,
            reverse("settings"),
            fetch_redirect_response=False,
        )

    def test_verify_email_rejects_get(self):
        response = self.client.get(reverse("verify_email_code"))
        self.assertEqual(response.status_code, 405)

    def test_verify_email_post_redirects_to_account_settings(self):
        response = self.client.post(
            reverse("verify_email_code"),
            {"code": "123456"},
        )
        self.assertRedirects(
            response,
            reverse("settings_account"),
            fetch_redirect_response=False,
        )


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)
class CustomSignupFormTests(TestCase):
    def test_signup_initializes_profile_identity_fields(self):
        form = CustomSignupForm(
            data={
                "full_name": "New Heartly User",
                "phone_number": "+256700000000",
                "gender": "female",
                "interested_in": "male",
                "date_of_birth": date(2000, 1, 1),
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

        user = User.objects.create_user(
            username="newheartlyuser",
            email="newheartlyuser@example.com",
            password="StrongPass123!",
        )

        form.signup(None, user)

        user.refresh_from_db()
        profile = Profile.objects.get(user=user)

        self.assertEqual(user.full_name, "New Heartly User")
        self.assertEqual(user.gender, "female")
        self.assertEqual(user.interested_in, "male")
        self.assertEqual(profile.display_name, "New Heartly User")
        self.assertEqual(profile.age, user.age)
        self.assertEqual(profile.gender, "woman")
        self.assertEqual(profile.interested_in, "men")
