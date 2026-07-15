from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Inspect Heartly email configuration and optionally "
        "send a delivery test."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            dest="recipient",
            default="",
            help="Recipient address for --send.",
        )
        parser.add_argument(
            "--send",
            action="store_true",
            help="Send one test email.",
        )

    def handle(self, *args, **options):
        backend = settings.EMAIL_BACKEND
        recipient = (options["recipient"] or "").strip()
        should_send = options["send"]

        self.stdout.write("Heartly email delivery check")
        self.stdout.write(f"Backend: {backend}")
        self.stdout.write(
            f"Default from: {settings.DEFAULT_FROM_EMAIL}"
        )
        self.stdout.write(
            "Verified-email enforcement: "
            f"{settings.HEARTLY_REQUIRE_VERIFIED_EMAIL}"
        )

        if backend.endswith("smtp.EmailBackend"):
            self.stdout.write(
                f"SMTP host configured: {bool(settings.EMAIL_HOST)}"
            )
            self.stdout.write(f"SMTP port: {settings.EMAIL_PORT}")
            self.stdout.write(
                "SMTP username configured: "
                f"{bool(settings.EMAIL_HOST_USER)}"
            )
            self.stdout.write(
                "SMTP password configured: "
                f"{bool(settings.EMAIL_HOST_PASSWORD)}"
            )
            self.stdout.write(f"SMTP TLS: {settings.EMAIL_USE_TLS}")
            self.stdout.write(f"SMTP SSL: {settings.EMAIL_USE_SSL}")

            missing = []
            if not settings.EMAIL_HOST:
                missing.append("DJANGO_EMAIL_HOST")
            if not settings.EMAIL_HOST_USER:
                missing.append("DJANGO_EMAIL_HOST_USER")
            if not settings.EMAIL_HOST_PASSWORD:
                missing.append("DJANGO_EMAIL_HOST_PASSWORD")

            if missing:
                raise CommandError(
                    "SMTP configuration is incomplete. Missing: "
                    + ", ".join(missing)
                )

        if not should_send:
            self.stdout.write(
                self.style.SUCCESS(
                    "Configuration inspection completed. "
                    "No email was sent."
                )
            )
            return

        if not recipient or "@" not in recipient:
            raise CommandError(
                "Provide a valid recipient with --to."
            )

        sent_count = send_mail(
            subject="Heartly email delivery test",
            message=(
                "Heartly email delivery is configured correctly. "
                "This message was sent by the email health command."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )

        if sent_count != 1:
            raise CommandError(
                "The email backend did not confirm one sent message."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Test email sent successfully to {recipient}."
            )
        )
