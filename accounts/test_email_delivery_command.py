from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


class EmailDeliveryCommandTests(SimpleTestCase):
    def test_inspection_does_not_send_email(self):
        output = StringIO()

        call_command(
            "check_email_delivery",
            stdout=output,
        )

        self.assertIn(
            "No email was sent",
            output.getvalue(),
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_send_uses_configured_backend(self):
        output = StringIO()

        call_command(
            "check_email_delivery",
            "--send",
            "--to",
            "owner@example.com",
            stdout=output,
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].to,
            ["owner@example.com"],
        )
        self.assertIn(
            "sent successfully",
            output.getvalue(),
        )

    @override_settings(
        EMAIL_BACKEND=(
            "django.core.mail.backends.smtp.EmailBackend"
        ),
        EMAIL_HOST="",
        EMAIL_HOST_USER="",
        EMAIL_HOST_PASSWORD="",
    )
    def test_incomplete_smtp_configuration_fails(self):
        with self.assertRaisesMessage(
            CommandError,
            "SMTP configuration is incomplete",
        ):
            call_command("check_email_delivery")
