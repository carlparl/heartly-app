import json
from collections import Counter
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from profiles.models import Profile


User = get_user_model()

USER_TO_PROFILE_GENDER = {
    "male": "man",
    "female": "woman",
    "non_binary": "non_binary",
    "prefer_not_to_say": "other",
}

USER_TO_PROFILE_INTERESTED_IN = {
    "male": "men",
    "female": "women",
    "both": "everyone",
}

SUMMARY_ORDER = [
    "total_users",
    "active_users",
    "staff_users",
    "missing_profiles",
    "missing_date_of_birth",
    "invalid_legal_age",
    "missing_profile_age",
    "invalid_profile_age",
    "profile_age_dob_mismatch",
    "gender_mismatch",
    "preference_mismatch",
    "legacy_friends_preference",
    "invalid_connection_goal",
    "display_name_full_name_mismatch",
    "incomplete_identity_profiles",
    "profiles_without_photo",
    "private_profiles",
    "moderated_profiles",
]


class Command(BaseCommand):
    help = (
        "Audit duplicate identity fields across CustomUser and Profile. "
        "This command is read-only and never modifies database records."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            help="Optional path for a JSON audit report.",
        )
        parser.add_argument(
            "--details",
            action="store_true",
            help=(
                "Include affected user IDs, usernames, and issue names in "
                "the JSON report. Emails and phone numbers are never included."
            ),
        )

    def handle(self, *args, **options):
        counters = Counter()
        details = []

        valid_profile_genders = {
            value for value, _label in Profile.GENDER_CHOICES
        }
        valid_profile_preferences = {
            value for value, _label in Profile.INTERESTED_IN_CHOICES
        }
        valid_connection_goals = {
            value
            for value, _label in Profile.CONNECTION_GOAL_CHOICES
        }

        users = User.objects.all().select_related("profile").order_by("id")

        for user in users.iterator():
            counters["total_users"] += 1
            issues = []

            if user.is_active:
                counters["active_users"] += 1

            if user.is_staff:
                counters["staff_users"] += 1

            try:
                profile = user.profile
            except Profile.DoesNotExist:
                profile = None
                self._record(
                    counters,
                    issues,
                    "missing_profiles",
                    "missing_profile",
                )

            date_of_birth = getattr(user, "date_of_birth", None)
            legal_age = getattr(user, "age", None)

            if date_of_birth is None:
                self._record(
                    counters,
                    issues,
                    "missing_date_of_birth",
                    "missing_date_of_birth",
                )

            if legal_age is None or not 18 <= legal_age <= 100:
                self._record(
                    counters,
                    issues,
                    "invalid_legal_age",
                    "invalid_legal_age",
                )

            if profile is not None:
                profile_age = getattr(profile, "age", None)

                if profile_age is None:
                    self._record(
                        counters,
                        issues,
                        "missing_profile_age",
                        "missing_profile_age",
                    )
                elif not 18 <= profile_age <= 100:
                    self._record(
                        counters,
                        issues,
                        "invalid_profile_age",
                        "invalid_profile_age",
                    )

                if (
                    legal_age is not None
                    and profile_age is not None
                    and legal_age != profile_age
                ):
                    self._record(
                        counters,
                        issues,
                        "profile_age_dob_mismatch",
                        "profile_age_dob_mismatch",
                    )

                expected_gender = USER_TO_PROFILE_GENDER.get(
                    getattr(user, "gender", "")
                )
                if expected_gender and profile.gender != expected_gender:
                    self._record(
                        counters,
                        issues,
                        "gender_mismatch",
                        "gender_mismatch",
                    )

                user_preference = getattr(user, "interested_in", "")
                expected_preference = USER_TO_PROFILE_INTERESTED_IN.get(
                    user_preference
                )

                if user_preference == "friends":
                    self._record(
                        counters,
                        issues,
                        "legacy_friends_preference",
                        "legacy_friends_preference",
                    )

                if (
                    expected_preference
                    and profile.interested_in != expected_preference
                ):
                    self._record(
                        counters,
                        issues,
                        "preference_mismatch",
                        "preference_mismatch",
                    )

                if (
                    profile.connection_goal
                    not in valid_connection_goals
                ):
                    self._record(
                        counters,
                        issues,
                        "invalid_connection_goal",
                        "invalid_connection_goal",
                    )

                user_full_name = (
                    getattr(user, "full_name", "")
                    or user.get_full_name()
                    or ""
                ).strip()
                display_name = (profile.display_name or "").strip()

                if (
                    user_full_name
                    and display_name
                    and user_full_name.casefold() != display_name.casefold()
                ):
                    self._record(
                        counters,
                        issues,
                        "display_name_full_name_mismatch",
                        "display_name_full_name_mismatch",
                    )

                identity_complete = (
                    bool(display_name)
                    and profile_age is not None
                    and 18 <= profile_age <= 100
                    and profile.gender in valid_profile_genders
                    and profile.interested_in in valid_profile_preferences
                    and profile.connection_goal in valid_connection_goals
                )
                if not identity_complete:
                    self._record(
                        counters,
                        issues,
                        "incomplete_identity_profiles",
                        "incomplete_identity_profile",
                    )

                if not getattr(profile, "profile_picture", None):
                    counters["profiles_without_photo"] += 1

                if not getattr(profile, "profile_visible", True):
                    counters["private_profiles"] += 1

                if getattr(profile, "hidden_by_moderation", False):
                    counters["moderated_profiles"] += 1

            if options["details"] and issues:
                details.append(
                    {
                        "user_id": user.id,
                        "username": user.get_username(),
                        "issues": sorted(set(issues)),
                    }
                )

        summary = {
            key: counters.get(key, 0)
            for key in SUMMARY_ORDER
        }

        report = {
            "generated_at": timezone.now().isoformat(),
            "read_only": True,
            "summary": summary,
            "details": details if options["details"] else [],
        }

        self.stdout.write(self.style.SUCCESS("Heartly profile identity audit"))
        self.stdout.write("Read-only: no database records were changed.\n")

        for key in SUMMARY_ORDER:
            label = key.replace("_", " ").title()
            self.stdout.write(f"{label}: {summary[key]}")

        output_path = options.get("output")
        if output_path:
            destination = Path(output_path).expanduser().resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(report, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            self.stdout.write(
                self.style.SUCCESS(f"\nJSON report: {destination}")
            )

    @staticmethod
    def _record(counters, issues, counter_name, issue_name):
        counters[counter_name] += 1
        issues.append(issue_name)
