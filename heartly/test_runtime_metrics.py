import json
import tempfile
from pathlib import Path

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from heartly.runtime_metrics import (
    record_request_metric,
    runtime_snapshot,
)


@override_settings(
    HEARTLY_RUNTIME_SAMPLE_MINIMUM=5,
    HEARTLY_RUNTIME_MAX_5XX_PERCENT=20,
    HEARTLY_RUNTIME_MAX_SLOW_PERCENT=40,
    HEARTLY_SLOW_REQUEST_MILLISECONDS=100,
)
class RuntimeMetricTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_aggregate_snapshot_contains_no_request_identity(self):
        record_request_metric(200, 10)
        record_request_metric(404, 20)
        record_request_metric(503, 150)

        snapshot = runtime_snapshot(hours=1)

        self.assertEqual(snapshot["requests"], 3)
        self.assertEqual(snapshot["responses_4xx"], 1)
        self.assertEqual(snapshot["responses_5xx"], 1)
        self.assertEqual(snapshot["slow_requests"], 1)
        self.assertNotIn("path", snapshot)
        self.assertNotIn("user", snapshot)

    def test_runtime_command_writes_privacy_safe_report(self):
        for _index in range(5):
            record_request_metric(200, 10)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "runtime.json"
            call_command(
                "audit_runtime_health",
                hours=1,
                output=str(output),
                fail_on_issues=True,
            )
            report = json.loads(output.read_text("utf-8"))

        self.assertTrue(report["sample_sufficient"])
        self.assertFalse(report["privacy"]["contains_paths"])
        self.assertFalse(report["database_records_changed"])

    def test_runtime_command_fails_elevated_error_rate(self):
        for _index in range(4):
            record_request_metric(200, 10)
        record_request_metric(500, 10)
        record_request_metric(500, 10)

        with self.assertRaises(CommandError):
            call_command(
                "audit_runtime_health",
                hours=1,
                fail_on_issues=True,
            )

    def test_request_middleware_exposes_timing_not_identity(self):
        response = self.client.get(reverse("health_liveness"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("app;dur=", response["Server-Timing"])
        self.assertIn("X-Request-ID", response)
