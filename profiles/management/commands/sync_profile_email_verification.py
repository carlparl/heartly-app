import json
from pathlib import Path

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from profiles.models import Profile


User = get_user_model()


class Command(BaseCommand):
    help = (
        "Dry-run or apply safe EmailAddress-to-Profile verification "
        "synchronization. Verification is never guessed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Apply safe changes. Without this flag the command "
                "is read-only."
            ),
        )
        parser.add_argument(
            "--details",
            action="store_true",
            help="Include per-user changes and verification issue codes.",
        )
        parser.add_argument(
            "--output",
            help="Optional JSON output path.",
        )

    def handle(self, *args, **options):
        report = self.build_report(
            apply_changes=bool(options["apply"]),
            include_details=bool(options["details"]),
        )
        self.print_summary(report)

        output_path = options.get("output")
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
            "verified_current_emails": 0,
            "unverified_current_emails": 0,
            "missing_current_emails": 0,
            "missing_email_addresses": 0,
            "profile_flag_mismatches": 0,
            "profiles_with_safe_changes": 0,
            "applied_profiles": 0,
            "verification_required_users": 0,
        }
        details = []

        users = User.objects.select_related("profile").order_by("id")

        with transaction.atomic():
            for user in users:
                summary["total_users"] += 1
                issues = []
                email = (getattr(user, "email", "") or "").strip()

                try:
                    profile = user.profile
                except Profile.DoesNotExist:
                    profile = None
                    summary["missing_profiles"] += 1
                    issues.append("missing_profile")
                else:
                    summary["profiles_checked"] += 1

                current_addresses = EmailAddress.objects.none()
                if not email:
                    authoritative_verified = False
                    summary["missing_current_emails"] += 1
                    issues.append("missing_current_email")
                else:
                    current_addresses = EmailAddress.objects.filter(
                        user=user,
                        email__iexact=email,
                    )
                    authoritative_verified = current_addresses.filter(
                        verified=True,
                    ).exists()

                    if authoritative_verified:
                        summary["verified_current_emails"] += 1
                    else:
                        summary["unverified_current_emails"] += 1
                        if current_addresses.exists():
                            issues.append("unverified_current_email")
                        else:
                            summary["missing_email_addresses"] += 1
                            issues.append("missing_email_address")

                if not authoritative_verified:
                    summary["verification_required_users"] += 1

                changes = {}
                if (
                    profile is not None
                    and profile.email_verified
                    != authoritative_verified
                ):
                    changes["email_verified"] = {
                        "from": bool(profile.email_verified),
                        "to": authoritative_verified,
                    }
                    summary["profile_flag_mismatches"] += 1
                    summary["profiles_with_safe_changes"] += 1

                applied = False
                if apply_changes and changes:
                    profile.email_verified = authoritative_verified
                    profile.save(
                        update_fields=[
                            "email_verified",
                            "updated_at",
                        ]
                    )
                    summary["applied_profiles"] += 1
                    applied = True

                if include_details and (changes or issues):
                    details.append(
                        {
                            "user_id": user.id,
                            "username": user.username,
                            "authoritative_verified": (
                                authoritative_verified
                            ),
                            "changes": changes,
                            "issues": issues,
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
        self.stdout.write("Heartly profile email verification sync")
        self.stdout.write(
            "Mode: APPLY"
            if report["mode"] == "apply"
            else "Mode: DRY RUN (no database changes)"
        )

        labels = [
            ("Total users", "total_users"),
            ("Profiles checked", "profiles_checked"),
            ("Missing profiles", "missing_profiles"),
            ("Verified current emails", "verified_current_emails"),
            (
                "Unverified current emails",
                "unverified_current_emails",
            ),
            ("Missing current emails", "missing_current_emails"),
            ("Missing EmailAddress rows", "missing_email_addresses"),
            ("Profile flag mismatches", "profile_flag_mismatches"),
            (
                "Profiles with safe changes",
                "profiles_with_safe_changes",
            ),
            ("Applied profiles", "applied_profiles"),
            (
                "Users requiring verification",
                "verification_required_users",
            ),
        ]

        for label, key in labels:
            self.stdout.write(f"{label}: {summary[key]}")
