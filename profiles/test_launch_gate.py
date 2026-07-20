import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone


User = get_user_model()


class LaunchGateTests(TestCase):
    def create_staff(self):
        return User.objects.create_user(
            username="launch-staff",
            email="launch-staff@example.com",
            password="StrongPass123!",
            is_staff=True,
        )

    def test_critical_launch_gate_passes_healthy_state(self):
        self.create_staff()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "launch.json"
            call_command(
                "audit_launch_gate",
                output=str(output),
                fail_on_issues=True,
            )
            report = json.loads(output.read_text("utf-8"))

        self.assertTrue(report["summary"]["ready_for_deploy"])
        self.assertEqual(report["summary"]["critical_failures"], 0)
        self.assertEqual(report["route_coverage"]["missing"], 0)
        self.assertFalse(report["database_records_changed"])

    def test_missing_staff_fails_critical_launch_gate(self):
        User.objects.filter(is_staff=True).update(
            is_staff=False,
            is_superuser=False,
        )
        with self.assertRaises(CommandError):
            call_command(
                "audit_launch_gate",
                fail_on_issues=True,
            )

    def test_warning_gate_detects_recovery_and_cleanup_followup(self):
        self.create_staff()
        Session.objects.create(
            session_key="launch-expired-session",
            session_data="e30:1test:invalid",
            expire_date=timezone.now(),
        )

        with self.assertRaises(CommandError):
            call_command(
                "audit_launch_gate",
                fail_on_warnings=True,
            )

    def test_fully_ready_with_current_recovery_metadata(self):
        self.create_staff()
        with override_settings(
            HEARTLY_BACKUP_PROVIDER="Neon",
            HEARTLY_RECOVERY_RUNBOOK_REFERENCE=(
                "internal-recovery-runbook"
            ),
            HEARTLY_LAST_RECOVERY_DRILL_AT=(
                timezone.now().isoformat()
            ),
        ):
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "launch.json"
                call_command(
                    "audit_launch_gate",
                    output=str(output),
                    fail_on_issues=True,
                    fail_on_warnings=True,
                )
                report = json.loads(output.read_text("utf-8"))

        self.assertTrue(report["summary"]["fully_ready"])
        self.assertEqual(report["summary"]["warning_failures"], 0)
