import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from profiles.data_retention import retention_summary


class Command(BaseCommand):
    help = (
        "Audit aggregate Heartly operational-data retention "
        "without deleting records."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            help="Optional aggregate JSON output path.",
        )
        parser.add_argument(
            "--fail-if-due",
            action="store_true",
            help="Exit with an error when cleanup is due.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        summary = retention_summary(now)
        report = {
            "generated_at": now.isoformat(),
            "read_only": True,
            "policy": {
                "email_code_days": (
                    settings.HEARTLY_RETENTION_EMAIL_CODE_DAYS
                ),
                "resolved_notification_days": (
                    settings.HEARTLY_RETENTION_RESOLVED_NOTIFICATION_DAYS
                ),
                "disabled_push_days": (
                    settings.HEARTLY_RETENTION_DISABLED_PUSH_DAYS
                ),
            },
            **summary,
        }

        self.stdout.write("Heartly data-retention audit")
        self.stdout.write("Read-only: no records changed")
        for name, count in summary["due"].items():
            self.stdout.write(
                f"{name.replace('_', ' ').title()}: {count}"
            )
        self.stdout.write(
            f"Total operational rows due: {summary['total_due']}"
        )
        self.stdout.write(
            "Safety reports and audit history are excluded."
        )

        output = options.get("output")
        if output:
            output_path = Path(output)
            output_path.write_text(
                json.dumps(report, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            self.stdout.write(f"JSON report: {output_path}")

        if options["fail_if_due"] and summary["total_due"]:
            raise CommandError(
                "Operational data cleanup is due."
            )
