import io
import json
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from profiles.data_retention import retention_summary
from profiles.management.commands.audit_operational_readiness import (
    recovery_drill_status,
)


def command_gate(command_name, **options):
    output = io.StringIO()
    try:
        call_command(
            command_name,
            stdout=output,
            stderr=output,
            **options,
        )
        return True
    except CommandError:
        return False


def route_gate():
    route_names = (
        "welcome",
        "account_login",
        "account_signup",
        "community_guidelines",
        "privacy_policy",
        "terms_of_service",
        "health_liveness",
        "health_readiness",
        "pwa_service_worker",
    )
    missing = 0
    for name in route_names:
        try:
            reverse(name)
        except NoReverseMatch:
            missing += 1
    return missing == 0, len(route_names), missing


class Command(BaseCommand):
    help = (
        "Run the aggregate Heartly launch gate across framework, "
        "safety, moderation, operations, privacy, and recovery checks."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--stale-hours",
            type=int,
            default=24,
            help="Moderation queue stale threshold (default: 24).",
        )
        parser.add_argument(
            "--output",
            help="Optional aggregate JSON output path.",
        )
        parser.add_argument(
            "--fail-on-issues",
            action="store_true",
            help="Exit with an error when a critical gate fails.",
        )
        parser.add_argument(
            "--fail-on-warnings",
            action="store_true",
            help="Also fail when retention or recovery follow-up is due.",
        )

    def handle(self, *args, **options):
        stale_hours = options["stale_hours"]
        if stale_hours < 1:
            raise CommandError("--stale-hours must be at least 1.")

        now = timezone.now()
        routes_passed, route_count, missing_routes = route_gate()
        critical_gates = {
            "django_system_checks": command_gate("check"),
            "safety_readiness": command_gate(
                "audit_safety_readiness",
                fail_on_issues=True,
            ),
            "moderation_queue": command_gate(
                "audit_moderation_queue",
                stale_hours=stale_hours,
                fail_on_issues=True,
            ),
            "operational_readiness": command_gate(
                "audit_operational_readiness",
                fail_on_issues=True,
            ),
            "public_routes": routes_passed,
        }

        retention = retention_summary(now)
        drill = recovery_drill_status(now)
        warning_gates = {
            "operational_cleanup_current": (
                retention["total_due"] == 0
            ),
            "backup_provider_documented": bool(
                settings.HEARTLY_BACKUP_PROVIDER
            ),
            "recovery_runbook_documented": bool(
                settings.HEARTLY_RECOVERY_RUNBOOK_REFERENCE
            ),
            "recovery_drill_current": bool(
                drill["valid"] and not drill["stale"]
            ),
        }
        critical_failures = sum(
            not passed for passed in critical_gates.values()
        )
        warning_failures = sum(
            not passed for passed in warning_gates.values()
        )
        report = {
            "generated_at": now.isoformat(),
            "database_records_changed": False,
            "summary": {
                "critical_failures": critical_failures,
                "warning_failures": warning_failures,
                "ready_for_deploy": critical_failures == 0,
                "fully_ready": (
                    critical_failures == 0
                    and warning_failures == 0
                ),
            },
            "critical_gates": critical_gates,
            "warning_gates": warning_gates,
            "route_coverage": {
                "expected": route_count,
                "missing": missing_routes,
            },
            "retention": {
                "operational_rows_due": retention["total_due"],
            },
            "recovery": {
                "drill_configured": drill["configured"],
                "drill_valid": drill["valid"],
                "drill_stale": drill["stale"],
                "drill_age_days": drill["age_days"],
            },
        }

        self.stdout.write("Heartly aggregate launch gate")
        self.stdout.write("Database records changed: no")
        for name, passed in critical_gates.items():
            self.stdout.write(
                f"Critical {name.replace('_', ' ')}: "
                f"{'PASS' if passed else 'FAIL'}"
            )
        for name, passed in warning_gates.items():
            self.stdout.write(
                f"Warning {name.replace('_', ' ')}: "
                f"{'PASS' if passed else 'FOLLOW-UP'}"
            )
        self.stdout.write(
            f"Critical failures: {critical_failures}"
        )
        self.stdout.write(
            f"Warning follow-ups: {warning_failures}"
        )

        output = options.get("output")
        if output:
            output_path = Path(output)
            output_path.write_text(
                json.dumps(report, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            self.stdout.write(f"JSON report: {output_path}")

        if (
            options["fail_on_issues"]
            or options["fail_on_warnings"]
        ) and critical_failures:
            raise CommandError("Critical launch gates failed.")
        if options["fail_on_warnings"] and warning_failures:
            raise CommandError("Launch warning follow-up is due.")
