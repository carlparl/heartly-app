import json
import tempfile
from datetime import date
from pathlib import Path

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
class AuditProfileIdentityCommandTests(TestCase):
    def create_user(self, username):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="StrongPass123!",
            full_name="Audit User",
            gender="male",
            interested_in="female",
            date_of_birth=date(2000, 1, 1),
        )
        profile = Profile.objects.get(user=user)
        profile.display_name = "Audit User"
        profile.age = user.age
        profile.gender = "man"
        profile.interested_in = "women"
        profile.profile_visible = True
        profile.hidden_by_moderation = False
        profile.save()
        return user, profile

    def run_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "audit.json"
            call_command(
                "audit_profile_identity",
                output=str(output),
                details=True,
                verbosity=0,
            )
            return json.loads(output.read_text(encoding="utf-8"))

    @staticmethod
    def details_for_user(report, user):
        return [
            detail
            for detail in report["details"]
            if detail.get("user_id") == user.id
        ]

    def test_command_is_read_only_and_reports_clean_identity(self):
        user, profile = self.create_user("clean_audit")
        original_user = {
            "full_name": user.full_name,
            "gender": user.gender,
            "interested_in": user.interested_in,
            "date_of_birth": user.date_of_birth,
        }
        original_profile = {
            "display_name": profile.display_name,
            "age": profile.age,
            "gender": profile.gender,
            "interested_in": profile.interested_in,
        }

        report = self.run_audit()

        user.refresh_from_db()
        profile.refresh_from_db()

        self.assertTrue(report["read_only"])
        self.assertGreaterEqual(
            report["summary"]["total_users"],
            1,
        )
        self.assertEqual(
            self.details_for_user(report, user),
            [],
        )
        self.assertEqual(
            {
                "full_name": user.full_name,
                "gender": user.gender,
                "interested_in": user.interested_in,
                "date_of_birth": user.date_of_birth,
            },
            original_user,
        )
        self.assertEqual(
            {
                "display_name": profile.display_name,
                "age": profile.age,
                "gender": profile.gender,
                "interested_in": profile.interested_in,
            },
            original_profile,
        )

    def test_command_reports_identity_mismatches(self):
        user, profile = self.create_user("mismatch_audit")
        profile.age = 31
        profile.gender = "woman"
        profile.interested_in = "men"
        profile.save()

        report = self.run_audit()
        summary = report["summary"]
        user_details = self.details_for_user(report, user)

        self.assertGreaterEqual(
            summary["profile_age_dob_mismatch"],
            1,
        )
        self.assertGreaterEqual(
            summary["gender_mismatch"],
            1,
        )
        self.assertGreaterEqual(
            summary["preference_mismatch"],
            1,
        )
        self.assertEqual(len(user_details), 1)
        self.assertEqual(
            user_details[0]["user_id"],
            user.id,
        )

    def test_command_reports_invalid_connection_goal(self):
        user, profile = self.create_user(
            "invalid_goal_audit"
        )
        profile.connection_goal = ""
        profile.save(
            update_fields=[
                "connection_goal",
                "updated_at",
            ]
        )

        report = self.run_audit()
        summary = report["summary"]
        user_details = self.details_for_user(
            report,
            user,
        )

        self.assertGreaterEqual(
            summary["invalid_connection_goal"],
            1,
        )
        self.assertEqual(len(user_details), 1)
        self.assertIn(
            "invalid_connection_goal",
            user_details[0]["issues"],
        )
