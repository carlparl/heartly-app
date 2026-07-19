from datetime import timedelta
from unittest.mock import patch

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import EmailVerificationCode


User = get_user_model()


@override_settings(
    HEARTLY_EMAIL_CODE_COOLDOWN_SECONDS=60,
    HEARTLY_EMAIL_CODE_MAX_SENDS_PER_HOUR=5,
    HEARTLY_EMAIL_CODE_MAX_SENDS_PER_DAY=10,
)
class EmailVerificationAbuseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="verification-limits",
            email="verification-limits@example.com",
            password="StrongPass123!",
        )
        EmailAddress.objects.update_or_create(
            user=self.user,
            email=self.user.email,
            defaults={
                "primary": True,
                "verified": False,
            },
        )
        self.client.force_login(self.user)

    def create_historical_code(self, created_at, *, used=False):
        code = EmailVerificationCode.objects.create(
            user=self.user,
            email=self.user.email,
            code_hash="unused-test-hash",
            expires_at=timezone.now() + timedelta(minutes=10),
            used_at=timezone.now() if used else None,
        )
        EmailVerificationCode.objects.filter(pk=code.pk).update(
            created_at=created_at
        )
        return code

    def post_send(self):
        return self.client.post(reverse("send_email_code"))

    @staticmethod
    def response_messages(response):
        return [
            str(message)
            for message in get_messages(response.wsgi_request)
        ]

    def test_successful_request_creates_one_code_and_email(self):
        response = self.post_send()

        self.assertRedirects(
            response,
            reverse("settings_account"),
            fetch_redirect_response=False,
        )
        self.assertEqual(EmailVerificationCode.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_used_code_still_enforces_cooldown(self):
        self.create_historical_code(timezone.now(), used=True)

        response = self.post_send()

        self.assertEqual(EmailVerificationCode.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(
            any(
                "Wait one minute" in message
                for message in self.response_messages(response)
            )
        )

    def test_hourly_send_cap_counts_all_codes(self):
        now = timezone.now()
        for offset in range(5):
            self.create_historical_code(
                now - timedelta(minutes=2 + offset),
                used=bool(offset % 2),
            )

        response = self.post_send()

        self.assertEqual(EmailVerificationCode.objects.count(), 5)
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(
            any(
                "Too many verification emails" in message
                for message in self.response_messages(response)
            )
        )

    def test_daily_send_cap_applies_after_hour_window(self):
        now = timezone.now()
        for offset in range(10):
            self.create_historical_code(
                now - timedelta(hours=2, minutes=offset),
                used=True,
            )

        response = self.post_send()

        self.assertEqual(EmailVerificationCode.objects.count(), 10)
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(
            any(
                "Too many verification emails" in message
                for message in self.response_messages(response)
            )
        )

    def test_failed_delivery_still_consumes_cooldown(self):
        with patch(
            "accounts.views.send_mail",
            side_effect=RuntimeError("delivery failed"),
        ):
            first_response = self.post_send()

        verification = EmailVerificationCode.objects.get()
        self.assertIsNotNone(verification.used_at)
        self.assertTrue(
            any(
                "could not send" in message
                for message in self.response_messages(first_response)
            )
        )

        second_response = self.post_send()

        self.assertEqual(EmailVerificationCode.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(
            any(
                "Wait one minute" in message
                for message in self.response_messages(second_response)
            )
        )
