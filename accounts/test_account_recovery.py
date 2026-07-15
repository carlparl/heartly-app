from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from accounts.models import EmailVerificationCode
from profiles.models import Profile


User = get_user_model()


class PasswordRecoveryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="recovery-user",
            email="recovery@example.com",
            password="OldStrongPass123!",
        )
        EmailAddress.objects.create(
            user=self.user,
            email=self.user.email,
            primary=True,
            verified=True,
        )

    def test_password_reset_page_loads(self):
        response = self.client.get(
            reverse("account_reset_password")
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "account/password_reset.html",
        )
        self.assertContains(response, "Recover your account")

    def test_known_email_sends_reset_message(self):
        response = self.client.post(
            reverse("account_reset_password"),
            {"email": self.user.email},
        )
        self.assertRedirects(
            response,
            reverse("account_reset_password_done"),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_unknown_email_uses_same_completion_route(self):
        known_response = self.client.post(
            reverse("account_reset_password"),
            {"email": self.user.email},
        )
        known_url = known_response.url
        mail.outbox.clear()

        unknown_response = self.client.post(
            reverse("account_reset_password"),
            {"email": "unknown@example.com"},
        )

        self.assertEqual(
            unknown_response.status_code,
            known_response.status_code,
        )
        self.assertEqual(unknown_response.url, known_url)
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_done_page_is_generic(self):
        response = self.client.get(
            reverse("account_reset_password_done")
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "account/password_reset_done.html",
        )
        self.assertContains(
            response,
            "If an account matches that email",
        )


class EmailChangeSafetyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="email-change-user",
            email="old@example.com",
            password="StrongPass123!",
        )
        self.profile = Profile.objects.get(user=self.user)
        EmailAddress.objects.create(
            user=self.user,
            email=self.user.email,
            primary=True,
            verified=True,
        )
        self.profile.refresh_from_db()

    def test_email_change_removes_verification_and_expires_codes(self):
        verification, _raw_code = (
            EmailVerificationCode.create_for_user(self.user)
        )

        self.user.email = "new@example.com"
        self.user.save(update_fields=["email"])

        self.profile.refresh_from_db()
        verification.refresh_from_db()

        self.assertFalse(self.profile.email_verified)
        self.assertIsNotNone(verification.used_at)
        self.assertTrue(
            EmailAddress.objects.filter(
                user=self.user,
                email="new@example.com",
                primary=True,
                verified=False,
            ).exists()
        )
        self.assertFalse(
            EmailAddress.objects.filter(
                user=self.user,
                email="old@example.com",
                primary=True,
            ).exists()
        )

    def test_non_email_update_does_not_expire_code(self):
        verification, _raw_code = (
            EmailVerificationCode.create_for_user(self.user)
        )

        self.user.full_name = "Updated Name"
        self.user.save(update_fields=["full_name"])

        verification.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertIsNone(verification.used_at)
        self.assertTrue(self.profile.email_verified)
