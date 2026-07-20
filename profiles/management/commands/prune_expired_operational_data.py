import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from profiles.data_retention import (
    PRESERVED_SAFETY_MODELS,
    retention_querysets,
)


class Command(BaseCommand):
    help = (
        "Dry-run or delete expired Heartly sessions, verification "
        "codes, resolved notifications, and disabled push endpoints."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply cleanup. Without this flag the command is read-only.",
        )
        parser.add_argument(
            "--output",
            help="Optional aggregate JSON output path.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        apply_changes = options["apply"]
        querysets = retention_querysets(now)
        due = {
            name: queryset.count()
            for name, queryset in querysets.items()
        }
        deleted = {name: 0 for name in querysets}

        if apply_changes:
            with transaction.atomic():
                for name, queryset in querysets.items():
                    primary_count = queryset.count()
                    queryset.delete()
                    deleted[name] = primary_count

        report = {
            "generated_at": now.isoformat(),
            "mode": "apply" if apply_changes else "dry_run",
            "due": due,
            "deleted": deleted,
            "preserved_safety_models": PRESERVED_SAFETY_MODELS,
        }

        self.stdout.write("Heartly operational-data cleanup")
        self.stdout.write(
            "Mode: APPLY"
            if apply_changes
            else "Mode: DRY RUN (no database changes)"
        )
        for name, count in due.items():
            self.stdout.write(
                f"{name.replace('_', ' ').title()}: "
                f"due={count} deleted={deleted[name]}"
            )
        self.stdout.write(
            "Safety reports and audit history were preserved."
        )

        output = options.get("output")
        if output:
            output_path = Path(output)
            output_path.write_text(
                json.dumps(report, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            self.stdout.write(f"JSON report: {output_path}")
