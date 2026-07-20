import json
from datetime import timedelta
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from .models import Profile, ProfileReport


User = get_user_model()


class SafetyReadinessAuditTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="readiness_staff",
            email="readiness-staff@example.com",
            password="StrongPass123!",
            is_staff=True,
        )

    def test_healthy_state_passes_and_writes_aggregate_json(self):
        with TemporaryDirectory() as directory:
            output = f"{directory}/safety-readiness.json"
            call_command(
                "audit_safety_readiness",
                output=output,
                fail_on_issues=True,
            )
            with open(output, encoding="utf-8") as report_file:
                report = json.load(report_file)

        self.assertTrue(report["read_only"])
        self.assertFalse(report["summary"]["has_issues"])
        self.assertEqual(
            report["summary"]["missing_report_evidence"],
            0,
        )

    def test_strict_mode_detects_enforcement_and_evidence_gaps(self):
        expired = User.objects.create_user(
            username="expired_restriction",
            email="expired-restriction@example.com",
            password="StrongPass123!",
            moderation_status=User.MODERATION_SUSPENDED,
            moderation_expires_at=(
                timezone.now() - timedelta(hours=1)
            ),
        )
        banned = User.objects.create_user(
            username="visible_banned",
            email="visible-banned@example.com",
            password="StrongPass123!",
            moderation_status=User.MODERATION_BANNED,
        )
        Profile.objects.filter(user=banned).update(
            hidden_by_moderation=False
        )
        ProfileReport.objects.create(
            reporter=expired,
            reported_user=banned,
            reason=ProfileReport.REASON_SPAM,
        )

        with self.assertRaises(CommandError):
            call_command(
                "audit_safety_readiness",
                fail_on_issues=True,
            )
