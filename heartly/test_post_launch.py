import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import TestCase, override_settings

from heartly.integrity_metrics import integrity_snapshot
from heartly.security import consume_rate_limit
from profiles.management.commands.audit_post_launch_readiness import (
    command_gate,
)
from profiles.management.commands.audit_production_closeout import (
    command_passes,
)


class PostLaunchReadinessTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_privacy_readiness_passes(self):
        call_command("audit_privacy_readiness", fail_on_issues=True)

    @override_settings(RATELIMIT_ENABLE=True)
    def test_integrity_readiness_passes(self):
        call_command("audit_integrity_readiness", fail_on_issues=True)

    @override_settings(
        RATELIMIT_ENABLE=True,
        HEARTLY_RATE_LIMITS={"reports": {"limit": 1, "window": 60}},
    )
    def test_rate_limit_activity_is_aggregate_and_identity_free(self):
        first = consume_rate_limit("reports", "hashed-identity", now=100)
        second = consume_rate_limit("reports", "hashed-identity", now=100)
        snapshot = integrity_snapshot(hours=1)

        self.assertTrue(first.allowed)
        self.assertFalse(second.allowed)
        self.assertEqual(snapshot["limited_requests"], 1)
        self.assertFalse(snapshot["contains_request_identity"])
        self.assertNotIn("hashed-identity", json.dumps(snapshot))

    def test_production_closeout_truthfully_fails_local_follow_up(self):
        with self.assertRaises(CommandError):
            call_command(
                "audit_production_closeout",
                runtime_hours=1,
                fail_on_issues=True,
            )

    def test_production_closeout_reports_unavailable_operational_data(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "closeout.json"
            with patch(
                "profiles.management.commands.audit_production_closeout."
                "retention_summary",
                side_effect=OperationalError("missing table"),
            ):
                call_command(
                    "audit_production_closeout",
                    runtime_hours=1,
                    output=str(output),
                )
            report = json.loads(output.read_text("utf-8"))

        self.assertFalse(report["checks"]["operational_data_available"])
        self.assertFalse(report["checks"]["operational_cleanup_current"])
        self.assertIn(
            "operational_data_available",
            report["failed_checks"],
        )

    def test_nested_database_errors_are_reported_as_follow_up(self):
        production_target = (
            "profiles.management.commands.audit_production_closeout."
            "call_command"
        )
        post_launch_target = (
            "profiles.management.commands.audit_post_launch_readiness."
            "call_command"
        )
        with patch(
            production_target,
            side_effect=OperationalError("database unavailable"),
        ):
            self.assertFalse(command_passes("audit_release_candidate"))
        with patch(
            post_launch_target,
            side_effect=OperationalError("database unavailable"),
        ):
            self.assertFalse(command_gate("audit_production_closeout"))

    def test_post_launch_report_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "post-launch.json"
            call_command(
                "audit_post_launch_readiness",
                runtime_hours=1,
                output=str(output),
            )
            report = json.loads(output.read_text("utf-8"))

        self.assertFalse(report["database_records_changed"])
        self.assertIn("production_closeout", report["gates"])
        self.assertFalse(
            report["integrity"]["contains_request_identity"]
        )
