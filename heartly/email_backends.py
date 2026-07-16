from __future__ import annotations

import base64
import json
import socket
from email.utils import parseaddr
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend


class BrevoAPIError(RuntimeError):
    """Raised when Brevo rejects or cannot receive an email request."""


def _parse_address(value):
    name, email = parseaddr(str(value or ""))
    email = email.strip()
    if not email:
        return None

    parsed = {"email": email}
    if name.strip():
        parsed["name"] = name.strip()
    return parsed


def _parse_addresses(values):
    parsed = []
    for value in values or []:
        address = _parse_address(value)
        if address:
            parsed.append(address)
    return parsed


def _alternative_parts(message):
    text_content = ""
    html_content = ""

    body = str(getattr(message, "body", "") or "")
    content_subtype = str(
        getattr(message, "content_subtype", "plain") or "plain"
    ).lower()

    if content_subtype == "html":
        html_content = body
    else:
        text_content = body

    for alternative in getattr(message, "alternatives", []) or []:
        content = getattr(alternative, "content", None)
        mimetype = getattr(alternative, "mimetype", None)

        if content is None and isinstance(alternative, (tuple, list)):
            if len(alternative) >= 2:
                content, mimetype = alternative[0], alternative[1]

        if content is None:
            continue

        mimetype = str(mimetype or "").lower()
        if mimetype == "text/html":
            html_content = str(content)
        elif mimetype == "text/plain":
            text_content = str(content)

    if not text_content and not html_content:
        text_content = " "

    return text_content, html_content


def _encode_attachments(message):
    encoded = []

    for attachment in getattr(message, "attachments", []) or []:
        filename = None
        content = None

        if hasattr(attachment, "get_payload"):
            filename = attachment.get_filename()
            content = attachment.get_payload(decode=True)
        else:
            filename = getattr(attachment, "filename", None)
            content = getattr(attachment, "content", None)

            if (
                filename is None
                and isinstance(attachment, (tuple, list))
                and len(attachment) >= 2
            ):
                filename, content = attachment[0], attachment[1]

        if not filename or content is None:
            continue

        if isinstance(content, str):
            content = content.encode(
                getattr(message, "encoding", None) or "utf-8"
            )
        elif not isinstance(content, bytes):
            content = bytes(content)

        encoded.append(
            {
                "name": str(filename),
                "content": base64.b64encode(content).decode("ascii"),
            }
        )

    return encoded


class BrevoAPIEmailBackend(BaseEmailBackend):
    """
    Deliver Django EmailMessage objects through Brevo's HTTPS API.

    Compatible with django-allauth, password reset emails, send_mail(),
    EmailMessage, and EmailMultiAlternatives.
    """

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = str(
            getattr(settings, "BREVO_API_KEY", "") or ""
        ).strip()
        self.sender_email = str(
            getattr(settings, "BREVO_SENDER_EMAIL", "") or ""
        ).strip()
        self.sender_name = str(
            getattr(settings, "BREVO_SENDER_NAME", "Heartly") or "Heartly"
        ).strip()
        self.api_url = str(
            getattr(
                settings,
                "BREVO_API_URL",
                "https://api.brevo.com/v3/smtp/email",
            )
            or "https://api.brevo.com/v3/smtp/email"
        ).strip()
        self.timeout = int(
            getattr(settings, "BREVO_API_TIMEOUT", 20) or 20
        )

    def _validate_configuration(self):
        missing = []
        if not self.api_key:
            missing.append("BREVO_API_KEY")
        if not self.sender_email:
            missing.append("BREVO_SENDER_EMAIL")
        if not self.api_url:
            missing.append("BREVO_API_URL")

        if missing:
            raise ImproperlyConfigured(
                "Brevo API email configuration is incomplete. Missing: "
                + ", ".join(missing)
            )

    def _build_payload(self, message):
        to_addresses = _parse_addresses(getattr(message, "to", []))
        cc_addresses = _parse_addresses(getattr(message, "cc", []))
        bcc_addresses = _parse_addresses(getattr(message, "bcc", []))

        if not (to_addresses or cc_addresses or bcc_addresses):
            return None

        sender = {"email": self.sender_email}
        if self.sender_name:
            sender["name"] = self.sender_name

        text_content, html_content = _alternative_parts(message)

        payload = {
            "sender": sender,
            "subject": str(getattr(message, "subject", "") or ""),
        }

        if to_addresses:
            payload["to"] = to_addresses
        if cc_addresses:
            payload["cc"] = cc_addresses
        if bcc_addresses:
            payload["bcc"] = bcc_addresses
        if text_content:
            payload["textContent"] = text_content
        if html_content:
            payload["htmlContent"] = html_content

        reply_to_values = getattr(message, "reply_to", []) or []
        if reply_to_values:
            reply_to = _parse_address(reply_to_values[0])
            if reply_to:
                payload["replyTo"] = reply_to

        attachments = _encode_attachments(message)
        if attachments:
            payload["attachment"] = attachments

        return payload

    @staticmethod
    def _http_error_detail(exc):
        try:
            raw_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw_body = ""

        if raw_body:
            try:
                decoded = json.loads(raw_body)
                detail = decoded.get("message") or decoded.get("code")
                if detail:
                    return str(detail)[:300]
            except (TypeError, ValueError):
                return raw_body[:300]

        return str(getattr(exc, "reason", "") or "request rejected")[:300]

    def _send_one(self, message):
        self._validate_configuration()
        payload = self._build_payload(message)
        if payload is None:
            return False

        request = Request(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "api-key": self.api_key,
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                status = getattr(response, "status", None)
                if status is None:
                    status = response.getcode()

                if not 200 <= int(status) < 300:
                    raise BrevoAPIError(
                        f"Brevo API returned HTTP {status}."
                    )
        except HTTPError as exc:
            detail = self._http_error_detail(exc)
            raise BrevoAPIError(
                f"Brevo API returned HTTP {exc.code}: {detail}"
            ) from exc
        except (URLError, TimeoutError, socket.timeout) as exc:
            reason = getattr(exc, "reason", exc)
            raise BrevoAPIError(
                f"Brevo API connection failed: {reason}"
            ) from exc

        return True

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        sent_count = 0
        for message in email_messages:
            try:
                if self._send_one(message):
                    sent_count += 1
            except Exception:
                if not self.fail_silently:
                    raise

        return sent_count
