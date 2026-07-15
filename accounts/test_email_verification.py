import re
from datetime import timedelta

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import EmailVerificationCode
from profiles.models import Profile


User = get_user_model()


class EmailVerificationFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="verify-user",
            email="verify@example.com",
            password="StrongPass123!",
        )
        self.profile = Profile.objects.get(user=self.user)
        self.client.force_login(self.user)

    def request_code(self):
        return self.client.post(reverse("send_email_code"))

    def latest_raw_code(self):
        match = re.search(
            r"\b(\d{6})\b",
            mail.outbox[-1].body,
        )
        self.assertIsNotNone(match)
        return match.group(1)

    def test_account_page_reports_unverified_email(self):
        response = self.client.get(
            reverse("settings_account")
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["email_verified"])
        self.assertContains(response, "Not verified")

    def test_send_code_creates_hashed_record_and_email(self):
        response = self.request_code()
        self.assertRedirects(
            response,
            reverse("settings_account"),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 1)

        verification = EmailVerificationCode.objects.get(
            user=self.user
        )
        raw_code = self.latest_raw_code()

        self.assertNotEqual(verification.code_hash, raw_code)
        self.assertTrue(verification.check_code(raw_code))

    def test_one_minute_cooldown_prevents_duplicate_email(self):
        self.request_code()
        first_count = EmailVerificationCode.objects.filter(
            user=self.user
        ).count()

        self.request_code()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            EmailVerificationCode.objects.filter(
                user=self.user
            ).count(),
            first_count,
        )

    def test_wrong_code_increments_attempts(self):
        self.request_code()
        verification = EmailVerificationCode.objects.get(
            user=self.user
        )

        self.client.post(
            reverse("verify_email_code"),
            {"code": "000000"},
        )

        verification.refresh_from_db()
        self.assertEqual(verification.attempts, 1)
        self.assertFalse(
            EmailAddress.objects.filter(
                user=self.user,
                email=self.user.email,
                verified=True,
            ).exists()
        )

    def test_correct_code_verifies_allauth_and_profile(self):
        self.request_code()
        raw_code = self.latest_raw_code()

        response = self.client.post(
            reverse("verify_email_code"),
            {"code": raw_code},
        )

        self.assertRedirects(
            response,
            reverse("settings_account"),
            fetch_redirect_response=False,
        )

        self.profile.refresh_from_db()
        verification = EmailVerificationCode.objects.get(
            user=self.user
        )

        self.assertIsNotNone(verification.used_at)
        self.assertTrue(self.profile.email_verified)
        self.assertTrue(
            EmailAddress.objects.filter(
                user=self.user,
                email=self.user.email,
                primary=True,
                verified=True,
            ).exists()
        )

    def test_expired_code_is_rejected(self):
        verification, raw_code = (
            EmailVerificationCode.create_for_user(
                self.user
            )
        )
        verification.expires_at = (
            timezone.now() - timedelta(minutes=1)
        )
        verification.save(update_fields=["expires_at"])

        self.client.post(
            reverse("verify_email_code"),
            {"code": raw_code},
        )

        verification.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertIsNotNone(verification.used_at)
        self.assertFalse(self.profile.email_verified)

    def test_verified_user_does_not_receive_another_code(self):
        EmailAddress.objects.create(
            user=self.user,
            email=self.user.email,
            primary=True,
            verified=True,
        )

        self.request_code()

        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(
            EmailVerificationCode.objects.filter(
                user=self.user
            ).exists()
        )

        self.profile.refresh_from_db()
        self.assertTrue(self.profile.email_verified)


class EmailVerificationSignalTests(TestCase):
    def test_email_address_signal_updates_profile_flag(self):
        user = User.objects.create_user(
            username="signal-user",
            email="signal@example.com",
            password="StrongPass123!",
        )
        profile = Profile.objects.get(user=user)

        email_address = EmailAddress.objects.create(
            user=user,
            email=user.email,
            primary=True,
            verified=True,
        )

        profile.refresh_from_db()
        self.assertTrue(profile.email_verified)

        email_address.verified = False
        email_address.save(update_fields=["verified"])

        profile.refresh_from_db()
        self.assertFalse(profile.email_verified)
