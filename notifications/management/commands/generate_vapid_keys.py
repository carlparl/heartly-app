import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def base64url(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class Command(BaseCommand):
    help = "Generate a VAPID key pair for Heartly browser push notifications."

    def add_arguments(self, parser):
        parser.add_argument(
            "--subject",
            default="mailto:admin@example.com",
            help="A mailto: or https: contact for the VAPID subject claim.",
        )

    def handle(self, *args, **options):
        private_key = ec.generate_private_key(ec.SECP256R1())
        private_der = private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_point = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )

        self.stdout.write("Store these as private Render environment variables:")
        self.stdout.write(f"VAPID_PUBLIC_KEY={base64url(public_point)}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={base64url(private_der)}")
        self.stdout.write(f"VAPID_SUBJECT={options['subject']}")
