import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


def accessibility_checks():
    base_path = settings.BASE_DIR / "templates" / "heartly" / "base.html"
    discover_path = settings.BASE_DIR / "templates" / "matches" / "discover.html"
    chat_path = settings.BASE_DIR / "templates" / "chat" / "chat_home.html"
    pagination_path = (
        settings.BASE_DIR
        / "templates"
        / "heartly"
        / "includes"
        / "pagination.html"
    )
    try:
        base = base_path.read_text(encoding="utf-8-sig")
        discover = discover_path.read_text(encoding="utf-8-sig")
        chat = chat_path.read_text(encoding="utf-8-sig")
        pagination = pagination_path.read_text(encoding="utf-8-sig")
    except OSError:
        return {"templates_readable": False}

    return {
        "templates_readable": True,
        "page_language_declared": '<html lang="en">' in base,
        "zoom_not_disabled": "user-scalable=no" not in base,
        "skip_link_present": 'href="#heartly-main-content"' in base,
        "main_landmark_target": 'id="heartly-main-content"' in base,
        "status_messages_announced": 'aria-live="polite"' in base,
        "keyboard_focus_visible": ":focus-visible" in base,
        "reduced_motion_supported": "prefers-reduced-motion" in base,
        "active_navigation_exposed": 'aria-current="page"' in base,
        "discover_search_labelled": (
            'aria-label="Search visible profiles"' in discover
        ),
        "chat_search_labelled": (
            'aria-label="Filter conversations on this page"' in chat
        ),
        "pagination_labelled": "aria-label=" in pagination,
        "pagination_current_page": 'aria-current="page"' in pagination,
    }


class Command(BaseCommand):
    help = "Audit Heartly's shared accessibility contract without writes."

    def add_arguments(self, parser):
        parser.add_argument("--output", help="Optional JSON output path.")
        parser.add_argument(
            "--fail-on-issues",
            action="store_true",
            help="Exit with an error when a shared accessibility gate fails.",
        )

    def handle(self, *args, **options):
        checks = accessibility_checks()
        failures = sorted(
            name for name, passed in checks.items() if not passed
        )
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

        self.stdout.write("Heartly accessibility readiness audit")
        self.stdout.write("Database records changed: no")
        self.stdout.write(f"Checks: {len(checks)}")
        self.stdout.write(f"Failures: {len(failures)}")

        output = options.get("output")
        if output:
            output_path = Path(output)
            output_path.write_text(
                json.dumps(report, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            self.stdout.write(f"JSON report: {output_path}")

        if options["fail_on_issues"] and failures:
            raise CommandError("Accessibility readiness issues detected.")
