import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from heartly.integrity_metrics import integrity_snapshot


class Command(BaseCommand):
    help = "Report aggregate rate-limit activity without request identities."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=2)
        parser.add_argument("--output", help="Optional JSON output path.")

    def handle(self, *args, **options):
        if not 1 <= options["hours"] <= 48:
            raise CommandError("--hours must be between 1 and 48.")
        snapshot = integrity_snapshot(hours=options["hours"])
        report = {
            "generated_at": timezone.now().isoformat(),
            "database_records_changed": False,
            "privacy": {
                "contains_request_identity": False,
                "contains_request_content": False,
            },
            "snapshot": snapshot,
        }
        self.stdout.write("Heartly integrity health audit")
        self.stdout.write("Database records changed: no")
        self.stdout.write(
            f"Rate-limited requests: {snapshot['limited_requests']}"
        )
        if options.get("output"):
            path = Path(options["output"])
            path.write_text(json.dumps(report, indent=2, sort_keys=True), "utf-8")
            self.stdout.write(f"JSON report: {path}")
