import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from chat.models import ChatReport
from feed.models import PostReport
from profiles.models import ModerationAction, Profile, ProfileReport


POLICY_ROUTES = (
    "community_guidelines",
    "privacy_policy",
    "terms_of_service",
)


def missing_evidence_count(model):
    return sum(
        not isinstance(snapshot, dict)
        or not snapshot.get("schema_version")
        for snapshot in model.objects.values_list(
            "evidence_snapshot",
            flat=True,
        )
    )


class Command(BaseCommand):
    help = (
        "Audit aggregate Heartly account enforcement, report "
        "evidence, staffing, and public policy readiness."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            help="Optional JSON output path.",
        )
        parser.add_argument(
            "--fail-on-issues",
            action="store_true",
            help="Exit with an error when readiness issues are found.",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        now = timezone.now()
        expired_suspensions = User.objects.filter(
            is_staff=False,
            is_superuser=False,
            moderation_status=User.MODERATION_SUSPENDED,
            moderation_expires_at__isnull=False,
            moderation_expires_at__lte=now,
        ).count()
        effective_suspended = User.objects.filter(
            is_staff=False,
            is_superuser=False,
            moderation_status=User.MODERATION_SUSPENDED,
        ).filter(
            Q(moderation_expires_at__isnull=True)
            | Q(moderation_expires_at__gt=now)
        ).count()
        banned = User.objects.filter(
            is_staff=False,
            is_superuser=False,
            moderation_status=User.MODERATION_BANNED,
        ).count()
        restricted_user_ids = User.objects.filter(
            is_staff=False,
            is_superuser=False,
        ).filter(
            Q(moderation_status=User.MODERATION_BANNED)
            | (
                Q(moderation_status=User.MODERATION_SUSPENDED)
                & (
                    Q(moderation_expires_at__isnull=True)
                    | Q(moderation_expires_at__gt=now)
                )
            )
        ).values_list("id", flat=True)
        visible_restricted_profiles = Profile.objects.filter(
            user_id__in=restricted_user_ids,
            hidden_by_moderation=False,
        ).count()

        evidence = {
            "profile_reports_missing": missing_evidence_count(
                ProfileReport
            ),
            "post_reports_missing": missing_evidence_count(
                PostReport
            ),
            "chat_reports_missing": missing_evidence_count(
                ChatReport
            ),
        }
        missing_evidence = sum(evidence.values())
        policy_routes = {}
        for route_name in POLICY_ROUTES:
            try:
                policy_routes[route_name] = reverse(route_name)
            except NoReverseMatch:
                policy_routes[route_name] = ""
        missing_policy_routes = sum(
            not path for path in policy_routes.values()
        )
        active_staff = User.objects.filter(
            is_active=True,
            is_staff=True,
        ).count()
        issues = {
            "expired_suspensions": expired_suspensions,
            "visible_restricted_profiles": (
                visible_restricted_profiles
            ),
            "missing_report_evidence": missing_evidence,
            "missing_policy_routes": missing_policy_routes,
            "no_active_staff": int(active_staff == 0),
        }
        has_issues = any(issues.values())
        report = {
            "generated_at": now.isoformat(),
            "read_only": True,
            "summary": {
                "active_staff": active_staff,
                "effective_suspensions": effective_suspended,
                "banned_accounts": banned,
                "expired_suspensions": expired_suspensions,
                "visible_restricted_profiles": (
                    visible_restricted_profiles
                ),
                "missing_report_evidence": missing_evidence,
                "account_audit_rows": (
                    ModerationAction.objects.filter(
                        source_type=(
                            ModerationAction.SOURCE_ACCOUNT
                        )
                    ).count()
                ),
                "has_issues": has_issues,
            },
            "evidence": evidence,
            "policy_routes": policy_routes,
            "issues": issues,
        }

        self.stdout.write("Heartly safety readiness audit")
        self.stdout.write("Read-only: no records changed")
        self.stdout.write(f"Active staff: {active_staff}")
        self.stdout.write(
            f"Effective suspensions: {effective_suspended}"
        )
        self.stdout.write(f"Banned accounts: {banned}")
        self.stdout.write(
            f"Expired suspensions: {expired_suspensions}"
        )
        self.stdout.write(
            "Visible restricted profiles: "
            f"{visible_restricted_profiles}"
        )
        self.stdout.write(
            f"Missing report evidence: {missing_evidence}"
        )
        self.stdout.write(
            f"Missing policy routes: {missing_policy_routes}"
        )

        output = options.get("output")
        if output:
            output_path = Path(output)
            output_path.write_text(
                json.dumps(report, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            self.stdout.write(f"JSON report: {output_path}")

        if options["fail_on_issues"] and has_issues:
            raise CommandError("Safety readiness issues detected.")
