import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from heartly.middleware import RATE_LIMIT_VIEW_GROUPS


REQUIRED_GROUPS = {
    "auth_login",
    "auth_signup",
    "auth_recovery",
    "email_verification",
    "reports",
    "blocking",
    "swipes",
    "messages",
    "feed_writes",
    "call_controls",
    "profile_writes",
    "sensitive_account",
    "websocket_events",
    "webrtc_signals",
}

REQUIRED_VIEW_LIMITS = {
    "account_login": "auth_login",
    "account_signup": "auth_signup",
    "delete_account": "sensitive_account",
    "data_export": "sensitive_account",
    "profiles:report_profile": "reports",
    "feed:report_post": "reports",
    "chat:report_thread_user": "reports",
    "matches:swipe": "swipes",
    "chat:send_message": "messages",
}


def integrity_checks():
    configured = set(settings.HEARTLY_RATE_LIMITS)
    missing_groups = sorted(REQUIRED_GROUPS - configured)
    missing_views = sorted(
        view
        for view, group in REQUIRED_VIEW_LIMITS.items()
        if RATE_LIMIT_VIEW_GROUPS.get(view) != group
    )
    backend = settings.CACHES["default"]["BACKEND"].lower()
    shared_cache = any(
        marker in backend for marker in ("redis", "memcached", "database")
    )
    production = bool(settings.IS_PRODUCTION)
    return {
        "rate_limit_middleware": (
            "heartly.middleware.AbuseRateLimitMiddleware"
            in settings.MIDDLEWARE
        ),
        "rate_limits_enabled": bool(settings.RATELIMIT_ENABLE),
        "required_groups_present": not missing_groups,
        "required_views_covered": not missing_views,
        "production_shared_cache": not production or shared_cache,
    }, missing_groups, missing_views


class Command(BaseCommand):
    help = "Audit Heartly abuse-resilience and rate-limit coverage."

    def add_arguments(self, parser):
        parser.add_argument("--output", help="Optional JSON output path.")
        parser.add_argument("--fail-on-issues", action="store_true")

    def handle(self, *args, **options):
        checks, missing_groups, missing_views = integrity_checks()
        failures = sorted(name for name, passed in checks.items() if not passed)
        report = {
            "generated_at": timezone.now().isoformat(),
            "database_records_changed": False,
            "summary": {"ready": not failures, "failures": len(failures)},
            "checks": checks,
            "missing_groups": missing_groups,
            "missing_views": missing_views,
        }
        self.stdout.write("Heartly integrity readiness audit")
        self.stdout.write("Database records changed: no")
        self.stdout.write(f"Missing groups: {len(missing_groups)}")
        self.stdout.write(f"Missing view limits: {len(missing_views)}")
        self.stdout.write(f"Failures: {len(failures)}")
        if options.get("output"):
            path = Path(options["output"])
            path.write_text(json.dumps(report, indent=2, sort_keys=True), "utf-8")
            self.stdout.write(f"JSON report: {path}")
        if options["fail_on_issues"] and failures:
            raise CommandError("Integrity readiness issues detected.")
