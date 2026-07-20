import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings


User = get_user_model()


class OperationalReadinessTests(TestCase):
    def setUp(self):
        User.objects.create_user(
            username="operations-staff",
            email="operations-staff@example.com",
            password="StrongPass123!",
            is_staff=True,
        )

    def test_healthy_test_environment_writes_aggregate_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "operations.json"
            call_command(
                "audit_operational_readiness",
                output=str(output),
                fail_on_issues=True,
            )
            report = json.loads(output.read_text("utf-8"))

        self.assertFalse(report["summary"]["has_issues"])
        self.assertTrue(report["database"]["connected"])
        self.assertTrue(report["cache"]["round_trip"])
        self.assertFalse(report["database_records_changed"])
        self.assertIn("users", report["inventory"])
        self.assertNotIn("HOST", json.dumps(report))
        self.assertNotIn("PASSWORD", json.dumps(report))

    @override_settings(
        HEARTLY_BACKUP_PROVIDER="",
        HEARTLY_RECOVERY_RUNBOOK_REFERENCE="",
        HEARTLY_LAST_RECOVERY_DRILL_AT="",
    )
    def test_strict_warning_mode_requires_recovery_metadata(self):
        with self.assertRaises(CommandError):
            call_command(
                "audit_operational_readiness",
                fail_on_warnings=True,
            )

    @override_settings(
        IS_PRODUCTION=True,
        DEBUG=True,
        RATELIMIT_ENABLE=False,
        USE_REDIS_CHANNEL_LAYER=False,
        HEARTLY_TRUST_X_FORWARDED_FOR=False,
        SESSION_COOKIE_SECURE=False,
        CSRF_COOKIE_SECURE=False,
        SECURE_SSL_REDIRECT=False,
        SECURE_HSTS_SECONDS=0,
    )
    def test_production_misconfiguration_fails_critical_mode(self):
        with self.assertRaises(CommandError):
            call_command(
                "audit_operational_readiness",
                fail_on_issues=True,
            )
