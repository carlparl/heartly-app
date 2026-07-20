import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from heartly.middleware import RATE_LIMIT_VIEW_GROUPS


def privacy_checks():
    try:
        export_route = reverse("data_export")
    except NoReverseMatch:
        export_route = ""
    template = (
        settings.BASE_DIR
        / "accounts"
        / "templates"
        / "accounts"
        / "data_export.html"
    )
    return {
        "data_export_route": bool(export_route),
        "data_export_template": template.exists(),
        "data_export_rate_limited": (
            RATE_LIMIT_VIEW_GROUPS.get("data_export")
            == "sensitive_account"
        ),
        "data_export_bound_valid": (
            100 <= settings.HEARTLY_DATA_EXPORT_MAX_RECORDS <= 50_000
        ),
        "account_deletion_route": bool(reverse("delete_account")),
        "privacy_policy_route": bool(reverse("privacy_policy")),
    }


class Command(BaseCommand):
    help = "Audit Heartly account privacy and lifecycle controls."

    def add_arguments(self, parser):
        parser.add_argument("--output", help="Optional JSON output path.")
        parser.add_argument("--fail-on-issues", action="store_true")

    def handle(self, *args, **options):
        checks = privacy_checks()
        failures = sorted(name for name, passed in checks.items() if not passed)
        report = {
            "generated_at": timezone.now().isoformat(),
            "database_records_changed": False,
            "summary": {
                "ready": not failures,
                "checks": len(checks),
                "failures": len(failures),
            },
            "checks": checks,
            "failed_checks": failures,
        }
        self.stdout.write("Heartly privacy readiness audit")
        self.stdout.write("Database records changed: no")
        self.stdout.write(f"Checks: {len(checks)}")
        self.stdout.write(f"Failures: {len(failures)}")
        if options.get("output"):
            path = Path(options["output"])
            path.write_text(json.dumps(report, indent=2, sort_keys=True), "utf-8")
            self.stdout.write(f"JSON report: {path}")
        if options["fail_on_issues"] and failures:
            raise CommandError("Privacy readiness issues detected.")
