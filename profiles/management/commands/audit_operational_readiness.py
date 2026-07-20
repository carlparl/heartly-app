import json
import uuid
from datetime import datetime, timezone as datetime_timezone
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from chat.models import ChatReport, ChatThread
from feed.models import Post, PostReport
from notifications.models import Notification
from profiles.models import ModerationAction, Profile, ProfileReport


def safe_count(queryset):
    try:
        return queryset.count()
    except Exception:
        return -1


def database_probe():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            connected = cursor.fetchone() == (1,)
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        pending = executor.migration_plan(targets)
        applied_count = len(
            executor.loader.applied_migrations
        )
        return {
            "connected": connected,
            "vendor": connection.vendor,
            "pending_migrations": len(pending),
            "applied_migrations": applied_count,
        }
    except Exception:
        return {
            "connected": False,
            "vendor": getattr(connection, "vendor", "unknown"),
            "pending_migrations": -1,
            "applied_migrations": 0,
        }


def cache_probe():
    backend = settings.CACHES["default"]["BACKEND"]
    shared = any(
        marker in backend.lower()
        for marker in ("redis", "memcached", "database")
    )
    probe_key = f"heartly:operational-probe:{uuid.uuid4().hex}"
    probe_value = uuid.uuid4().hex
    round_trip = False
    try:
        cache.set(probe_key, probe_value, timeout=30)
        round_trip = cache.get(probe_key) == probe_value
    except Exception:
        round_trip = False
    finally:
        try:
            cache.delete(probe_key)
        except Exception:
            pass

    return {
        "backend": backend,
        "shared": shared,
        "round_trip": round_trip,
    }


def recovery_drill_status(now):
    raw_value = settings.HEARTLY_LAST_RECOVERY_DRILL_AT
    if not raw_value:
        return {
            "configured": False,
            "valid": False,
            "age_days": None,
            "stale": True,
        }

    parsed = parse_datetime(raw_value)
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(raw_value)
        except ValueError:
            parsed = None

    if parsed is None:
        return {
            "configured": True,
            "valid": False,
            "age_days": None,
            "stale": True,
        }

    if timezone.is_naive(parsed):
        parsed = parsed.replace(tzinfo=datetime_timezone.utc)
    age_days = max(0, (now - parsed).days)
    return {
        "configured": True,
        "valid": True,
        "age_days": age_days,
        "stale": (
            age_days
            > settings.HEARTLY_RECOVERY_DRILL_MAX_AGE_DAYS
        ),
    }


class Command(BaseCommand):
    help = (
        "Audit aggregate Heartly database, cache, session, "
        "rate-limit, security, and recovery readiness."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            help="Optional aggregate JSON output path.",
        )
        parser.add_argument(
            "--fail-on-issues",
            action="store_true",
            help="Exit with an error when critical issues are found.",
        )
        parser.add_argument(
            "--fail-on-warnings",
            action="store_true",
            help=(
                "Also fail when backup or recovery-drill metadata "
                "needs attention."
            ),
        )

    def handle(self, *args, **options):
        now = timezone.now()
        database = database_probe()
        cache_status = cache_probe()
        User = get_user_model()
        active_staff = safe_count(
            User.objects.filter(
                is_active=True,
                is_staff=True,
            )
        )

        middleware = set(settings.MIDDLEWARE)
        session_security = {
            "middleware_configured": (
                "heartly.middleware.SessionSecurityMiddleware"
                in middleware
            ),
            "idle_timeout_seconds": (
                settings.HEARTLY_SESSION_IDLE_TIMEOUT_SECONDS
            ),
            "absolute_timeout_seconds": (
                settings.HEARTLY_SESSION_ABSOLUTE_TIMEOUT_SECONDS
            ),
            "secure_cookie": bool(
                getattr(settings, "SESSION_COOKIE_SECURE", False)
            ),
            "http_only": bool(settings.SESSION_COOKIE_HTTPONLY),
            "same_site": settings.SESSION_COOKIE_SAMESITE,
        }
        rate_limits = {
            "middleware_configured": (
                "heartly.middleware.AbuseRateLimitMiddleware"
                in middleware
            ),
            "enabled": bool(settings.RATELIMIT_ENABLE),
            "configured_groups": len(
                settings.HEARTLY_RATE_LIMITS
            ),
            "shared_cache": cache_status["shared"],
            "trusted_proxy_identity": bool(
                settings.HEARTLY_TRUST_X_FORWARDED_FOR
            ),
        }
        recovery_drill = recovery_drill_status(now)
        recovery = {
            "backup_provider_configured": bool(
                settings.HEARTLY_BACKUP_PROVIDER
            ),
            "runbook_reference_configured": bool(
                settings.HEARTLY_RECOVERY_RUNBOOK_REFERENCE
            ),
            "drill": recovery_drill,
        }

        production = bool(settings.IS_PRODUCTION)
        issues = {
            "database_unavailable": int(
                not database["connected"]
            ),
            "pending_migrations": max(
                0,
                database["pending_migrations"],
            ),
            "cache_unavailable": int(
                not cache_status["round_trip"]
            ),
            "no_active_staff": int(active_staff == 0),
            "session_middleware_missing": int(
                not session_security["middleware_configured"]
            ),
            "invalid_session_bounds": int(
                session_security["absolute_timeout_seconds"]
                < session_security["idle_timeout_seconds"]
            ),
            "rate_limit_middleware_missing": int(
                not rate_limits["middleware_configured"]
            ),
            "production_debug_enabled": int(
                production and settings.DEBUG
            ),
            "production_sqlite_database": int(
                production and database["vendor"] == "sqlite"
            ),
            "production_unshared_cache": int(
                production and not cache_status["shared"]
            ),
            "production_rate_limits_disabled": int(
                production and not rate_limits["enabled"]
            ),
            "production_insecure_session_cookie": int(
                production and not session_security["secure_cookie"]
            ),
            "production_insecure_csrf_cookie": int(
                production
                and not getattr(
                    settings,
                    "CSRF_COOKIE_SECURE",
                    False,
                )
            ),
            "production_ssl_redirect_disabled": int(
                production
                and not getattr(
                    settings,
                    "SECURE_SSL_REDIRECT",
                    False,
                )
            ),
            "production_hsts_disabled": int(
                production
                and int(
                    getattr(settings, "SECURE_HSTS_SECONDS", 0)
                )
                < 3600
            ),
            "production_proxy_identity_disabled": int(
                production
                and not rate_limits["trusted_proxy_identity"]
            ),
            "production_redis_channels_disabled": int(
                production
                and not settings.USE_REDIS_CHANNEL_LAYER
            ),
        }
        warnings = {
            "backup_provider_missing": int(
                not recovery["backup_provider_configured"]
            ),
            "recovery_runbook_missing": int(
                not recovery["runbook_reference_configured"]
            ),
            "recovery_drill_missing_or_invalid": int(
                not recovery_drill["valid"]
            ),
            "recovery_drill_stale": int(
                recovery_drill["valid"]
                and recovery_drill["stale"]
            ),
        }
        has_issues = any(issues.values())
        has_warnings = any(warnings.values())

        inventory = {
            "users": safe_count(User.objects.all()),
            "profiles": safe_count(Profile.objects.all()),
            "posts": safe_count(Post.objects.all()),
            "chat_threads": safe_count(
                ChatThread.objects.all()
            ),
            "notifications": safe_count(
                Notification.objects.all()
            ),
            "profile_reports": safe_count(
                ProfileReport.objects.all()
            ),
            "post_reports": safe_count(
                PostReport.objects.all()
            ),
            "chat_reports": safe_count(
                ChatReport.objects.all()
            ),
            "moderation_audit_rows": (
                safe_count(ModerationAction.objects.all())
            ),
        }
        report = {
            "generated_at": now.isoformat(),
            "database_records_changed": False,
            "environment": {
                "production": production,
            },
            "summary": {
                "active_staff": active_staff,
                "has_issues": has_issues,
                "has_warnings": has_warnings,
            },
            "database": database,
            "cache": cache_status,
            "session_security": session_security,
            "rate_limits": rate_limits,
            "recovery": recovery,
            "inventory": inventory,
            "issues": issues,
            "warnings": warnings,
        }

        self.stdout.write("Heartly operational readiness audit")
        self.stdout.write("Database records changed: no")
        self.stdout.write(
            f"Database connected: {database['connected']}"
        )
        self.stdout.write(
            "Pending migrations: "
            f"{database['pending_migrations']}"
        )
        self.stdout.write(
            f"Cache round trip: {cache_status['round_trip']}"
        )
        self.stdout.write(
            f"Shared cache: {cache_status['shared']}"
        )
        self.stdout.write(f"Active staff: {active_staff}")
        self.stdout.write(
            f"Critical issues: {sum(issues.values())}"
        )
        self.stdout.write(
            f"Recovery warnings: {sum(warnings.values())}"
        )

        output = options.get("output")
        if output:
            output_path = Path(output)
            output_path.write_text(
                json.dumps(report, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            self.stdout.write(f"JSON report: {output_path}")

        if (
            options["fail_on_issues"]
            or options["fail_on_warnings"]
        ) and has_issues:
            raise CommandError(
                "Operational readiness issues detected."
            )
        if options["fail_on_warnings"] and has_warnings:
            raise CommandError(
                "Operational recovery warnings detected."
            )
