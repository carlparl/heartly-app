import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from profiles.identity import (
    confirmed_legal_age,
    mapped_profile_gender,
    mapped_profile_preference,
)
from profiles.models import Profile


User = get_user_model()


class Command(BaseCommand):
    help = (
        "Dry-run or apply safe CustomUser-to-Profile identity "
        "normalization. Unresolved values are never guessed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply safe changes. Without this flag the command is read-only.",
        )
        parser.add_argument(
            "--details",
            action="store_true",
            help="Include per-user changes and unresolved issue codes.",
        )
        parser.add_argument(
            "--output",
            help="Optional JSON output path.",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        include_details = bool(options["details"])
        output_path = options.get("output")

        report = self.build_report(
            apply_changes=apply_changes,
            include_details=include_details,
        )

        self.print_summary(report)

        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(report, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            self.stdout.write("")
            self.stdout.write(f"JSON report: {path}")

    def build_report(self, *, apply_changes, include_details):
        summary = {
            "total_users": 0,
            "profiles_checked": 0,
            "missing_profiles": 0,
            "profiles_with_changes": 0,
            "applied_profiles": 0,
            "gender_updates": 0,
            "preference_updates": 0,
            "connection_goal_updates": 0,
            "age_updates": 0,
            "unresolved_profiles": 0,
        }
        details = []

        users = (
            User.objects
            .select_related("profile")
            .order_by("id")
        )

        with transaction.atomic():
            for user in users:
                summary["total_users"] += 1

                try:
                    profile = user.profile
                except Profile.DoesNotExist:
                    summary["missing_profiles"] += 1
                    summary["unresolved_profiles"] += 1
                    if include_details:
                        details.append(
                            {
                                "user_id": user.id,
                                "username": user.username,
                                "changes": {},
                                "unresolved": ["missing_profile"],
                                "applied": False,
                            }
                        )
                    continue

                summary["profiles_checked"] += 1
                changes = {}
                unresolved = []

                target_gender = mapped_profile_gender(
                    getattr(user, "gender", "")
                )
                if target_gender:
                    if profile.gender != target_gender:
                        changes["gender"] = {
                            "from": profile.gender,
                            "to": target_gender,
                        }
                elif getattr(user, "gender", ""):
                    unresolved.append("unsupported_user_gender")
                else:
                    unresolved.append("missing_user_gender")

                target_preference = mapped_profile_preference(
                    getattr(user, "interested_in", "")
                )
                if target_preference:
                    if profile.interested_in != target_preference:
                        changes["interested_in"] = {
                            "from": profile.interested_in,
                            "to": target_preference,
                        }
                elif getattr(user, "interested_in", "") == "friends":
                    if (
                        profile.connection_goal
                        != Profile.CONNECTION_FRIENDSHIP
                    ):
                        changes["connection_goal"] = {
                            "from": profile.connection_goal,
                            "to": Profile.CONNECTION_FRIENDSHIP,
                        }
                    unresolved.append("legacy_friends_preference")
                elif getattr(user, "interested_in", ""):
                    unresolved.append("unsupported_user_preference")
                else:
                    unresolved.append("missing_user_preference")

                legal_age = confirmed_legal_age(user)
                if legal_age is None:
                    if getattr(user, "date_of_birth", None) is None:
                        unresolved.append("missing_date_of_birth")
                    else:
                        unresolved.append("invalid_legal_age")
                elif profile.age != legal_age:
                    changes["age"] = {
                        "from": profile.age,
                        "to": legal_age,
                    }

                if changes:
                    summary["profiles_with_changes"] += 1
                    if "gender" in changes:
                        summary["gender_updates"] += 1
                    if "interested_in" in changes:
                        summary["preference_updates"] += 1
                    if "connection_goal" in changes:
                        summary["connection_goal_updates"] += 1
                    if "age" in changes:
                        summary["age_updates"] += 1

                if unresolved:
                    summary["unresolved_profiles"] += 1

                applied = False
                if apply_changes and changes:
                    update_fields = []

                    for field_name, change in changes.items():
                        setattr(profile, field_name, change["to"])
                        update_fields.append(field_name)

                    update_fields.append("updated_at")
                    profile.save(update_fields=update_fields)
                    summary["applied_profiles"] += 1
                    applied = True

                if include_details and (changes or unresolved):
                    details.append(
                        {
                            "user_id": user.id,
                            "username": user.username,
                            "changes": changes,
                            "unresolved": unresolved,
                            "applied": applied,
                        }
                    )

        return {
            "generated_at": timezone.now().isoformat(),
            "mode": "apply" if apply_changes else "dry-run",
            "read_only": not apply_changes,
            "summary": summary,
            "details": details if include_details else [],
        }

    def print_summary(self, report):
        summary = report["summary"]
        self.stdout.write("Heartly profile identity normalization")
        self.stdout.write(
            "Mode: APPLY" if report["mode"] == "apply"
            else "Mode: DRY RUN (no database changes)"
        )

        labels = [
            ("Total users", "total_users"),
            ("Profiles checked", "profiles_checked"),
            ("Missing profiles", "missing_profiles"),
            ("Profiles with safe changes", "profiles_with_changes"),
            ("Applied profiles", "applied_profiles"),
            ("Gender updates", "gender_updates"),
            ("Preference updates", "preference_updates"),
            (
                "Connection goal updates",
                "connection_goal_updates",
            ),
            ("Age updates", "age_updates"),
            ("Unresolved profiles", "unresolved_profiles"),
        ]

        for label, key in labels:
            self.stdout.write(f"{label}: {summary[key]}")
