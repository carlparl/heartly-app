import io
import json
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from heartly.runtime_metrics import runtime_snapshot
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


class Command(BaseCommand):
    help = (
        "Run Heartly's final release-candidate gate across safety, "
        "operations, performance, accessibility, runtime, and recovery."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--stale-hours",
            type=int,
            default=24,
            help="Moderation queue stale threshold (default: 24).",
        )
        parser.add_argument(
            "--runtime-hours",
            type=int,
            default=2,
            help="Runtime metric window count (default: 2).",
        )
        parser.add_argument("--output", help="Optional JSON output path.")
        parser.add_argument(
            "--fail-on-issues",
            action="store_true",
            help="Exit with an error when a critical release gate fails.",
        )
        parser.add_argument(
            "--fail-on-warnings",
            action="store_true",
            help="Also fail when operational follow-up remains.",
        )

    def handle(self, *args, **options):
        if options["stale_hours"] < 1:
            raise CommandError("--stale-hours must be at least 1.")
        if not 1 <= options["runtime_hours"] <= 48:
            raise CommandError("--runtime-hours must be between 1 and 48.")

        now = timezone.now()
        critical_gates = {
            "launch_readiness": command_gate(
                "audit_launch_gate",
                stale_hours=options["stale_hours"],
                fail_on_issues=True,
            ),
            "performance_readiness": command_gate(
                "audit_performance_readiness",
                fail_on_issues=True,
            ),
            "accessibility_readiness": command_gate(
                "audit_accessibility_readiness",
                fail_on_issues=True,
            ),
            "runtime_health": command_gate(
                "audit_runtime_health",
                hours=options["runtime_hours"],
                fail_on_issues=True,
            ),
        }

        retention = retention_summary(now)
        runtime = runtime_snapshot(
            now=now,
            hours=options["runtime_hours"],
        )
        drill = recovery_drill_status(now)
        warning_gates = {
            "operational_cleanup_current": (
                retention["total_due"] == 0
            ),
            "runtime_sample_sufficient": (
                runtime["requests"]
                >= settings.HEARTLY_RUNTIME_SAMPLE_MINIMUM
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
                "release_candidate": critical_failures == 0,
                "fully_ready": (
                    critical_failures == 0
                    and warning_failures == 0
                ),
            },
            "critical_gates": critical_gates,
            "warning_gates": warning_gates,
            "runtime": {
                "requests": runtime["requests"],
                "error_5xx_percent": runtime["error_5xx_percent"],
                "slow_request_percent": runtime["slow_request_percent"],
            },
            "retention": {
                "operational_rows_due": retention["total_due"],
            },
        }

        self.stdout.write("Heartly final release-candidate audit")
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
        self.stdout.write(f"Critical failures: {critical_failures}")
        self.stdout.write(f"Warning follow-ups: {warning_failures}")

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
            raise CommandError("Critical release-candidate gates failed.")
        if options["fail_on_warnings"] and warning_failures:
            raise CommandError("Release-candidate follow-up is due.")
