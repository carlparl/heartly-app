import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from accounts.models import CustomUser
from chat.models import ChatThread
from notifications.models import Notification
from profiles.models import Profile


EXPECTED_INDEXES = {
    Profile: {"profiles_discovery_idx"},
    ChatThread: {
        "chat_thread_user1_idx",
        "chat_thread_user2_idx",
    },
    Notification: {"notify_recipient_recent_idx"},
}


def index_inventory():
    missing = []
    present = []
    try:
        with connection.cursor() as cursor:
            for model, expected_names in EXPECTED_INDEXES.items():
                constraints = connection.introspection.get_constraints(
                    cursor,
                    model._meta.db_table,
                )
                actual = {
                    name
                    for name, details in constraints.items()
                    if details.get("index")
                }
                for name in sorted(expected_names):
                    target = f"{model._meta.label}.{name}"
                    if name in actual:
                        present.append(target)
                    else:
                        missing.append(target)

            user_constraints = connection.introspection.get_constraints(
                cursor,
                CustomUser._meta.db_table,
            )
            dob_indexed = any(
                details.get("index")
                and details.get("columns") == ["date_of_birth"]
                for details in user_constraints.values()
            )
            if dob_indexed:
                present.append("accounts.CustomUser.date_of_birth")
            else:
                missing.append("accounts.CustomUser.date_of_birth")
    except Exception:
        return {
            "database_connected": False,
            "present": [],
            "missing": [
                f"{model._meta.label}.{name}"
                for model, names in EXPECTED_INDEXES.items()
                for name in names
            ] + ["accounts.CustomUser.date_of_birth"],
        }

    return {
        "database_connected": True,
        "present": sorted(present),
        "missing": sorted(missing),
    }


def collection_bounds():
    values = {
        "discover_page_size": settings.HEARTLY_DISCOVER_PAGE_SIZE,
        "discover_candidate_limit": (
            settings.HEARTLY_DISCOVER_CANDIDATE_LIMIT
        ),
        "notification_page_size": settings.HEARTLY_NOTIFICATION_PAGE_SIZE,
        "chat_thread_page_size": settings.HEARTLY_CHAT_THREAD_LIMIT,
        "chat_message_limit": settings.HEARTLY_CHAT_MESSAGE_LIMIT,
    }
    valid = (
        1 <= values["discover_page_size"] <= 60
        and values["discover_page_size"]
        <= values["discover_candidate_limit"] <= 1000
        and 1 <= values["notification_page_size"] <= 100
        and 1 <= values["chat_thread_page_size"] <= 200
        and 1 <= values["chat_message_limit"] <= 250
    )
    return values, valid


class Command(BaseCommand):
    help = (
        "Audit Heartly collection bounds, production cache, and indexes "
        "used by high-traffic member views."
    )

    def add_arguments(self, parser):
        parser.add_argument("--output", help="Optional JSON output path.")
        parser.add_argument(
            "--fail-on-issues",
            action="store_true",
            help="Exit with an error when a performance gate fails.",
        )

    def handle(self, *args, **options):
        indexes = index_inventory()
        bounds, bounds_valid = collection_bounds()
        cache_backend = settings.CACHES["default"]["BACKEND"]
        shared_cache = any(
            marker in cache_backend.lower()
            for marker in ("redis", "memcached", "database")
        )
        production = bool(settings.IS_PRODUCTION)
        issues = {
            "database_unavailable": int(
                not indexes["database_connected"]
            ),
            "missing_performance_indexes": len(indexes["missing"]),
            "invalid_collection_bounds": int(not bounds_valid),
            "production_unshared_cache": int(
                production and not shared_cache
            ),
        }
        report = {
            "generated_at": timezone.now().isoformat(),
            "database_records_changed": False,
            "summary": {
                "ready": not any(issues.values()),
                "issue_count": sum(issues.values()),
            },
            "collection_bounds": bounds,
            "cache": {
                "backend": cache_backend,
                "shared": shared_cache,
            },
            "indexes": indexes,
            "issues": issues,
        }

        self.stdout.write("Heartly performance readiness audit")
        self.stdout.write("Database records changed: no")
        self.stdout.write(f"Collection bounds valid: {bounds_valid}")
        self.stdout.write(f"Shared cache: {shared_cache}")
        self.stdout.write(
            f"Missing performance indexes: {len(indexes['missing'])}"
        )

        output = options.get("output")
        if output:
            output_path = Path(output)
            output_path.write_text(
                json.dumps(report, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            self.stdout.write(f"JSON report: {output_path}")

        if options["fail_on_issues"] and any(issues.values()):
            raise CommandError("Performance readiness issues detected.")
