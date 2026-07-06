from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse


User = get_user_model()


class AccountsRoutesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="StrongPass123!"
        )
        self.client.login(username="testuser", password="StrongPass123!")

    def test_settings_home_loads(self):
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 200)

    def test_settings_account_loads(self):
        response = self.client.get(reverse("settings_account"))
        self.assertEqual(response.status_code, 200)

    def test_settings_privacy_loads(self):
        response = self.client.get(reverse("settings_privacy"))
        self.assertEqual(response.status_code, 200)

    def test_notifications_home_loads(self):
        response = self.client.get(reverse("notifications_home"))
        self.assertEqual(response.status_code, 200)

    def test_settings_help_loads(self):
        response = self.client.get(reverse("settings_help"))
        self.assertEqual(response.status_code, 200)

    def test_settings_about_loads(self):
        response = self.client.get(reverse("settings_about"))
        self.assertEqual(response.status_code, 200)

    def test_verify_email_page_loads(self):
        response = self.client.get(reverse("verify_email_code"))
        self.assertEqual(response.status_code, 200)