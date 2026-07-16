import io
import json
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMultiAlternatives
from django.test import SimpleTestCase, override_settings

from heartly.email_backends import BrevoAPIError


class _SuccessfulResponse:
    status = 201

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def getcode(self):
        return self.status


@override_settings(
    EMAIL_BACKEND="heartly.email_backends.BrevoAPIEmailBackend",
    BREVO_API_KEY="test-api-key",
    BREVO_SENDER_EMAIL="verified@example.com",
    BREVO_SENDER_NAME="Heartly",
    BREVO_API_URL="https://api.brevo.com/v3/smtp/email",
    BREVO_API_TIMEOUT=20,
)
class BrevoAPIEmailBackendTests(SimpleTestCase):
    @patch("heartly.email_backends.urlopen")
    def test_sends_text_and_html_through_https_api(self, mocked_urlopen):
        mocked_urlopen.return_value = _SuccessfulResponse()

        message = EmailMultiAlternatives(
            subject="Verify your email",
            body="Your verification code is 123456.",
            from_email="Heartly <ignored@example.com>",
            to=["Member <member@example.com>"],
            reply_to=["Support <support@example.com>"],
        )
        message.attach_alternative(
            "<p>Your verification code is <strong>123456</strong>.</p>",
            "text/html",
        )

        self.assertEqual(message.send(), 1)

        request = mocked_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        headers = dict(request.header_items())

        self.assertEqual(
            request.full_url,
            "https://api.brevo.com/v3/smtp/email",
        )
        self.assertEqual(headers["Api-key"], "test-api-key")
        self.assertEqual(
            payload["sender"],
            {"email": "verified@example.com", "name": "Heartly"},
        )
        self.assertEqual(
            payload["to"],
            [{"email": "member@example.com", "name": "Member"}],
        )
        self.assertEqual(
            payload["replyTo"],
            {"email": "support@example.com", "name": "Support"},
        )
        self.assertIn("123456", payload["textContent"])
        self.assertIn("<strong>123456</strong>", payload["htmlContent"])
        mocked_urlopen.assert_called_once()
        self.assertEqual(mocked_urlopen.call_args.kwargs["timeout"], 20)

    @patch("heartly.email_backends.urlopen")
    def test_brevo_http_error_is_clear_and_does_not_expose_key(
        self,
        mocked_urlopen,
    ):
        from urllib.error import HTTPError

        mocked_urlopen.side_effect = HTTPError(
            "https://api.brevo.com/v3/smtp/email",
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"message":"Key not found"}'),
        )

        message = EmailMultiAlternatives(
            subject="Test",
            body="Test",
            to=["member@example.com"],
        )

        with self.assertRaisesMessage(
            BrevoAPIError,
            "Brevo API returned HTTP 401: Key not found",
        ):
            message.send()

        try:
            message.send()
        except BrevoAPIError as exc:
            self.assertNotIn("test-api-key", str(exc))

    @override_settings(BREVO_API_KEY="")
    def test_missing_api_key_fails_before_network_request(self):
        message = EmailMultiAlternatives(
            subject="Test",
            body="Test",
            to=["member@example.com"],
        )

        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "BREVO_API_KEY",
        ):
            message.send()

    @patch("heartly.email_backends.urlopen")
    def test_fail_silently_returns_zero(self, mocked_urlopen):
        from urllib.error import URLError

        mocked_urlopen.side_effect = URLError("network unavailable")

        message = EmailMultiAlternatives(
            subject="Test",
            body="Test",
            to=["member@example.com"],
        )

        self.assertEqual(message.send(fail_silently=True), 0)
