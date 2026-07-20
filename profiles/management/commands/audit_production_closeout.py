import io
import json
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError
from django.utils import timezone

from heartly.runtime_metrics import runtime_snapshot
from profiles.data_retention import retention_summary
from profiles.management.commands.audit_operational_readiness import (
    recovery_drill_status,
)


def command_passes(name, **options):
    stream = io.StringIO()
    try:
        call_command(name, stdout=stream, stderr=stream, **options)
        return True
    except (CommandError, DatabaseError):
        return False


class Command(BaseCommand):
    help = "Run Heartly's strict, evidence-based production closeout gate."

    def add_arguments(self, parser):
        parser.add_argument("--runtime-hours", type=int, default=2)
        parser.add_argument("--output", help="Optional JSON output path.")
        parser.add_argument("--fail-on-issues", action="store_true")

    def handle(self, *args, **options):
        hours = options["runtime_hours"]
        if not 1 <= hours <= 48:
            raise CommandError("--runtime-hours must be between 1 and 48.")

        now = timezone.now()
        runtime = runtime_snapshot(now=now, hours=hours)
        drill = recovery_drill_status(now)
        try:
            retention = retention_summary(now)
            operational_data_available = True
        except DatabaseError:
            retention = {"total_due": None}
            operational_data_available = False
        cache_backend = settings.CACHES["default"]["BACKEND"].lower()
        shared_cache = any(
            marker in cache_backend
            for marker in ("redis", "memcached", "database")
        )
        checks = {
            "production_environment": bool(settings.IS_PRODUCTION),
            "debug_disabled": not settings.DEBUG,
            "shared_cache": shared_cache,
            "strict_release_candidate": command_passes(
                "audit_release_candidate",
                runtime_hours=hours,
                fail_on_warnings=True,
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
            "operational_data_available": operational_data_available,
            "operational_cleanup_current": (
                operational_data_available and retention["total_due"] == 0
            ),
        }
        failures = sorted(name for name, passed in checks.items() if not passed)
        report = {
            "generated_at": now.isoformat(),
            "database_records_changed": False,
            "summary": {
                "closed_out": not failures,
                "checks": len(checks),
                "failures": len(failures),
            },
            "checks": checks,
            "failed_checks": failures,
            "runtime": {
                "requests": runtime["requests"],
                "error_5xx_percent": runtime["error_5xx_percent"],
                "slow_request_percent": runtime["slow_request_percent"],
            },
            "recovery": {
                "drill_configured": drill["configured"],
                "drill_valid": drill["valid"],
                "drill_stale": drill["stale"],
                "drill_age_days": drill["age_days"],
            },
        }
        self.stdout.write("Heartly production closeout audit")
        self.stdout.write("Database records changed: no")
        for name, passed in checks.items():
            self.stdout.write(
                f"{name.replace('_', ' ')}: {'PASS' if passed else 'FOLLOW-UP'}"
            )
        self.stdout.write(f"Failures: {len(failures)}")
        if options.get("output"):
            path = Path(options["output"])
            path.write_text(json.dumps(report, indent=2, sort_keys=True), "utf-8")
            self.stdout.write(f"JSON report: {path}")
        if options["fail_on_issues"] and failures:
            raise CommandError("Production closeout follow-up remains.")
