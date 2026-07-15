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
class NormalizeProfileIdentityCommandTests(TestCase):
    def create_user(
        self,
        username,
        *,
        gender="male",
        interested_in="both",
        date_of_birth=date(2000, 1, 1),
    ):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="StrongPass123!",
            full_name="Normalization User",
            gender=gender,
            interested_in=interested_in,
            date_of_birth=date_of_birth,
        )
        profile = Profile.objects.get(user=user)
        return user, profile

    def run_command(self, *, apply_changes=False):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "normalization.json"
            arguments = [
                "--details",
                "--output",
                str(output),
            ]
            if apply_changes:
                arguments.append("--apply")

            call_command(
                "normalize_profile_identity",
                *arguments,
                verbosity=0,
            )
            return json.loads(
                output.read_text(encoding="utf-8")
            )

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

    def test_dry_run_reports_changes_without_writing(self):
        user, profile = self.create_user("dry_run_identity")
        profile.gender = Profile.GENDER_WOMAN
        profile.interested_in = Profile.INTERESTED_IN_MEN
        profile.age = 31
        profile.save()

        original = {
            "gender": profile.gender,
            "interested_in": profile.interested_in,
            "age": profile.age,
        }

        report = self.run_command(apply_changes=False)
        profile.refresh_from_db()
        detail = self.detail_for(report, user)

        self.assertTrue(report["read_only"])
        self.assertEqual(
            {
                "gender": profile.gender,
                "interested_in": profile.interested_in,
                "age": profile.age,
            },
            original,
        )
        self.assertEqual(
            detail["changes"]["gender"]["to"],
            Profile.GENDER_MAN,
        )
        self.assertEqual(
            detail["changes"]["interested_in"]["to"],
            Profile.INTERESTED_IN_EVERYONE,
        )
        self.assertEqual(
            detail["changes"]["age"]["to"],
            user.age,
        )
        self.assertFalse(detail["applied"])

    def test_apply_updates_only_safe_values_and_is_idempotent(self):
        safe_user, safe_profile = self.create_user(
            "safe_identity"
        )
        safe_profile.gender = Profile.GENDER_WOMAN
        safe_profile.interested_in = Profile.INTERESTED_IN_MEN
        safe_profile.age = None
        safe_profile.save()

        unresolved_user, unresolved_profile = self.create_user(
            "unresolved_identity",
            gender="prefer_not_to_say",
            interested_in="friends",
            date_of_birth=None,
        )
        unresolved_profile.gender = Profile.GENDER_OTHER
        unresolved_profile.interested_in = (
            Profile.INTERESTED_IN_WOMEN
        )
        unresolved_profile.age = None
        unresolved_profile.save()

        first_report = self.run_command(apply_changes=True)
        safe_profile.refresh_from_db()
        unresolved_profile.refresh_from_db()

        self.assertFalse(first_report["read_only"])
        self.assertEqual(
            safe_profile.gender,
            Profile.GENDER_MAN,
        )
        self.assertEqual(
            safe_profile.interested_in,
            Profile.INTERESTED_IN_EVERYONE,
        )
        self.assertEqual(safe_profile.age, safe_user.age)

        unresolved_detail = self.detail_for(
            first_report,
            unresolved_user,
        )
        self.assertIn(
            "unsupported_user_gender",
            unresolved_detail["unresolved"],
        )
        self.assertIn(
            "legacy_friends_preference",
            unresolved_detail["unresolved"],
        )
        self.assertIn(
            "missing_date_of_birth",
            unresolved_detail["unresolved"],
        )
        self.assertEqual(
            unresolved_profile.gender,
            Profile.GENDER_OTHER,
        )
        self.assertEqual(
            unresolved_profile.interested_in,
            Profile.INTERESTED_IN_WOMEN,
        )
        self.assertIsNone(unresolved_profile.age)

        second_report = self.run_command(apply_changes=True)
        safe_detail = self.detail_for(second_report, safe_user)

        self.assertEqual(
            second_report["summary"]["applied_profiles"],
            0,
        )
        self.assertIsNone(safe_detail)
