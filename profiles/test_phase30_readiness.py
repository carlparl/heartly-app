import json
import tempfile
from pathlib import Path

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from heartly.runtime_metrics import record_request_metric


class PhaseThirtyReadinessTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_accessibility_contract_passes(self):
        call_command(
            "audit_accessibility_readiness",
            fail_on_issues=True,
        )

    def test_performance_indexes_and_bounds_pass(self):
        call_command(
            "audit_performance_readiness",
            fail_on_issues=True,
        )

    def test_release_candidate_passes_critical_gates(self):
        call_command(
            "audit_release_candidate",
            fail_on_issues=True,
        )

    def test_warning_strict_release_passes_complete_metadata(self):
        for _index in range(20):
            record_request_metric(200, 20)

        with override_settings(
            HEARTLY_RUNTIME_SAMPLE_MINIMUM=20,
            HEARTLY_BACKUP_PROVIDER="managed-provider",
            HEARTLY_RECOVERY_RUNBOOK_REFERENCE="internal-runbook",
            HEARTLY_LAST_RECOVERY_DRILL_AT=timezone.now().isoformat(),
        ):
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "release.json"
                call_command(
                    "audit_release_candidate",
                    runtime_hours=1,
                    output=str(output),
                    fail_on_issues=True,
                    fail_on_warnings=True,
                )
                report = json.loads(output.read_text("utf-8"))

        self.assertTrue(report["summary"]["fully_ready"])
        self.assertEqual(report["summary"]["critical_failures"], 0)

    def test_warning_strict_release_detects_follow_up(self):
        with self.assertRaises(CommandError):
            call_command(
                "audit_release_candidate",
                runtime_hours=1,
                fail_on_warnings=True,
            )
