import io
import json
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError
from django.utils import timezone

from heartly.integrity_metrics import integrity_snapshot


def command_gate(name, **options):
    stream = io.StringIO()
    try:
        call_command(name, stdout=stream, stderr=stream, **options)
        return True
    except (CommandError, DatabaseError):
        return False


class Command(BaseCommand):
    help = "Certify Heartly's complete post-launch operational baseline."

    def add_arguments(self, parser):
        parser.add_argument("--runtime-hours", type=int, default=2)
        parser.add_argument("--output", help="Optional JSON output path.")
        parser.add_argument("--fail-on-issues", action="store_true")

    def handle(self, *args, **options):
        hours = options["runtime_hours"]
        if not 1 <= hours <= 48:
            raise CommandError("--runtime-hours must be between 1 and 48.")
        gates = {
            "production_closeout": command_gate(
                "audit_production_closeout",
                runtime_hours=hours,
                fail_on_issues=True,
            ),
            "privacy_readiness": command_gate(
                "audit_privacy_readiness",
                fail_on_issues=True,
            ),
            "integrity_readiness": command_gate(
                "audit_integrity_readiness",
                fail_on_issues=True,
            ),
        }
        failures = sorted(name for name, passed in gates.items() if not passed)
        integrity = integrity_snapshot(hours=hours)
        report = {
            "generated_at": timezone.now().isoformat(),
            "database_records_changed": False,
            "summary": {
                "post_launch_ready": not failures,
                "failures": len(failures),
            },
            "gates": gates,
            "failed_gates": failures,
            "integrity": {
                "limited_requests": integrity["limited_requests"],
                "contains_request_identity": False,
                "contains_request_content": False,
            },
        }
        self.stdout.write("Heartly post-launch readiness audit")
        self.stdout.write("Database records changed: no")
        for name, passed in gates.items():
            self.stdout.write(
                f"{name.replace('_', ' ')}: {'PASS' if passed else 'FOLLOW-UP'}"
            )
        self.stdout.write(f"Failures: {len(failures)}")
        if options.get("output"):
            path = Path(options["output"])
            path.write_text(json.dumps(report, indent=2, sort_keys=True), "utf-8")
            self.stdout.write(f"JSON report: {path}")
        if options["fail_on_issues"] and failures:
            raise CommandError("Post-launch readiness follow-up remains.")
