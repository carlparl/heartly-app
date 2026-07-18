import json
import tempfile
from pathlib import Path

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from profiles.models import Profile


User = get_user_model()


@override_settings(
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher"
    ]
)
class SyncProfileEmailVerificationCommandTests(TestCase):
    def create_user(self, username, *, email=None, verified=False):
        email = email if email is not None else f"{username}@example.com"
        user = User.objects.create_user(
            username=username,
            email=email,
            password="StrongPass123!",
        )
        profile = Profile.objects.get(user=user)

        if email:
            EmailAddress.objects.update_or_create(
                user=user,
                email=email,
                defaults={
                    "primary": True,
                    "verified": verified,
                },
            )

        return user, profile

    def run_command(self, *, apply_changes=False):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "email-sync.json"
            arguments = ["--details", "--output", str(output)]
            if apply_changes:
                arguments.append("--apply")

            call_command(
                "sync_profile_email_verification",
                *arguments,
                verbosity=0,
            )
            return json.loads(output.read_text(encoding="utf-8"))

    @staticmethod
    def detail_for(report, user):
        return next(
            (
                detail
                for detail in report["details"]
                if detail["user_id"] == user.id
            ),
            None,
        )

    def test_dry_run_reports_verified_mismatch_without_writing(self):
        user, profile = self.create_user(
            "verified_dry_run",
            verified=True,
        )
        profile.email_verified = False
        profile.save(update_fields=["email_verified", "updated_at"])

        report = self.run_command(apply_changes=False)
        profile.refresh_from_db()
        detail = self.detail_for(report, user)

        self.assertTrue(report["read_only"])
        self.assertFalse(profile.email_verified)
        self.assertEqual(
            detail["changes"]["email_verified"],
            {"from": False, "to": True},
        )
        self.assertFalse(detail["applied"])

    def test_apply_corrects_both_directions_and_is_idempotent(self):
        verified_user, verified_profile = self.create_user(
            "verified_apply",
            verified=True,
        )
        verified_profile.email_verified = False
        verified_profile.save(
            update_fields=["email_verified", "updated_at"]
        )

        unverified_user, unverified_profile = self.create_user(
            "unverified_apply",
            verified=False,
        )
        unverified_profile.email_verified = True
        unverified_profile.save(
            update_fields=["email_verified", "updated_at"]
        )

        first_report = self.run_command(apply_changes=True)
        verified_profile.refresh_from_db()
        unverified_profile.refresh_from_db()

        self.assertTrue(verified_profile.email_verified)
        self.assertFalse(unverified_profile.email_verified)
        self.assertEqual(
            first_report["summary"]["applied_profiles"],
            2,
        )
        self.assertIn(
            "unverified_current_email",
            self.detail_for(
                first_report,
                unverified_user,
            )["issues"],
        )

        second_report = self.run_command(apply_changes=True)
        self.assertEqual(
            second_report["summary"]["applied_profiles"],
            0,
        )
        self.assertIsNone(
            self.detail_for(second_report, verified_user)
        )

    def test_missing_email_and_profile_are_reported_without_guessing(self):
        missing_email_user, missing_email_profile = self.create_user(
            "missing_email",
            email="",
        )
        missing_email_profile.email_verified = True
        missing_email_profile.save(
            update_fields=["email_verified", "updated_at"]
        )

        missing_profile_user, missing_profile = self.create_user(
            "missing_profile",
            verified=True,
        )
        missing_profile.delete()

        report = self.run_command(apply_changes=True)
        missing_email_profile.refresh_from_db()

        self.assertFalse(missing_email_profile.email_verified)
        self.assertIn(
            "missing_current_email",
            self.detail_for(
                report,
                missing_email_user,
            )["issues"],
        )
        self.assertIn(
            "missing_profile",
            self.detail_for(
                report,
                missing_profile_user,
            )["issues"],
        )
        self.assertEqual(report["summary"]["missing_profiles"], 1)
