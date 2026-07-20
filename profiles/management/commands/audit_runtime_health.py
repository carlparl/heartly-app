import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from heartly.runtime_metrics import runtime_snapshot


class Command(BaseCommand):
    help = (
        "Audit aggregate Heartly request error and latency counters. "
        "No paths, users, query strings, or request bodies are stored."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=2,
            help="Number of hourly metric windows to aggregate (default: 2).",
        )
        parser.add_argument(
            "--output",
            help="Optional aggregate JSON output path.",
        )
        parser.add_argument(
            "--fail-on-issues",
            action="store_true",
            help="Exit with an error when sampled thresholds are exceeded.",
        )
        parser.add_argument(
            "--fail-on-warnings",
            action="store_true",
            help="Also fail when too few requests have been sampled.",
        )

    def handle(self, *args, **options):
        hours = options["hours"]
        if not 1 <= hours <= 48:
            raise CommandError("--hours must be between 1 and 48.")

        snapshot = runtime_snapshot(
            now=timezone.now(),
            hours=hours,
        )
        sample_sufficient = (
            snapshot["requests"]
            >= settings.HEARTLY_RUNTIME_SAMPLE_MINIMUM
        )
        issues = {
            "elevated_5xx_rate": int(
                sample_sufficient
                and snapshot["error_5xx_percent"]
                > settings.HEARTLY_RUNTIME_MAX_5XX_PERCENT
            ),
            "elevated_slow_request_rate": int(
                sample_sufficient
                and snapshot["slow_request_percent"]
                > settings.HEARTLY_RUNTIME_MAX_SLOW_PERCENT
            ),
        }
        warnings = {
            "insufficient_sample": int(not sample_sufficient),
        }
        report = {
            "generated_at": timezone.now().isoformat(),
            "database_records_changed": False,
            "privacy": {
                "contains_paths": False,
                "contains_user_ids": False,
                "contains_request_content": False,
            },
            "thresholds": {
                "sample_minimum": settings.HEARTLY_RUNTIME_SAMPLE_MINIMUM,
                "max_5xx_percent": settings.HEARTLY_RUNTIME_MAX_5XX_PERCENT,
                "max_slow_percent": settings.HEARTLY_RUNTIME_MAX_SLOW_PERCENT,
            },
            "sample_sufficient": sample_sufficient,
            "snapshot": snapshot,
            "issues": issues,
            "warnings": warnings,
        }

        self.stdout.write("Heartly runtime health audit")
        self.stdout.write("Database records changed: no")
        self.stdout.write(f"Requests sampled: {snapshot['requests']}")
        self.stdout.write(
            f"5xx rate: {snapshot['error_5xx_percent']}%"
        )
        self.stdout.write(
            f"Slow request rate: {snapshot['slow_request_percent']}%"
        )
        self.stdout.write(
            f"Average duration: {snapshot['average_duration_ms']} ms"
        )
        self.stdout.write(f"Sample sufficient: {sample_sufficient}")

        output = options.get("output")
        if output:
            output_path = Path(output)
            output_path.write_text(
                json.dumps(report, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            self.stdout.write(f"JSON report: {output_path}")

        has_issues = any(issues.values())
        has_warnings = any(warnings.values())
        if (
            options["fail_on_issues"]
            or options["fail_on_warnings"]
        ) and has_issues:
            raise CommandError("Runtime health thresholds were exceeded.")
        if options["fail_on_warnings"] and has_warnings:
            raise CommandError("Runtime health sample is incomplete.")
