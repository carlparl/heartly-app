import json
from datetime import timedelta
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from chat.models import ChatReport, ChatThread
from feed.models import Post, PostReport
from notifications.activity import notify_post_report
from profiles.models import ProfileReport


User = get_user_model()


@override_settings(
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher"
    ]
)
class ModerationQueueAuditCommandTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="queue_staff",
            email="queue-staff@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.reporter = User.objects.create_user(
            username="queue_reporter",
            email="queue-reporter@example.com",
            password="StrongPass123!",
        )
        self.target = User.objects.create_user(
            username="queue_target",
            email="queue-target@example.com",
            password="StrongPass123!",
        )

    def create_pending_reports(self):
        profile_report = ProfileReport.objects.create(
            reporter=self.reporter,
            reported_user=self.target,
            reason=ProfileReport.REASON_SPAM,
        )
        ProfileReport.objects.filter(
            pk=profile_report.pk
        ).update(
            created_at=(
                timezone.now() - timedelta(hours=30)
            )
        )

        post = Post.objects.create(
            author=self.target,
            content="Queue audit marker",
        )
        post_report = PostReport.objects.create(
            post=post,
            reporter=self.reporter,
            reason=PostReport.REASON_SPAM,
        )
        notify_post_report(post_report)

        thread = ChatThread.get_or_create_between(
            self.reporter,
            self.target,
        )
        ChatReport.objects.create(
            thread=thread,
            reporter=self.reporter,
            reported_user=self.target,
            reason=ChatReport.REASON_SPAM,
        )

    def test_audit_reports_queue_age_and_alert_gaps(self):
        self.create_pending_reports()

        with TemporaryDirectory() as directory:
            output = f"{directory}/moderation-queue.json"
            call_command(
                "audit_moderation_queue",
                stale_hours=24,
                output=output,
            )
            with open(output, encoding="utf-8") as report_file:
                report = json.load(report_file)

        summary = report["summary"]
        self.assertTrue(report["read_only"])
        active_staff = User.objects.filter(
            is_active=True,
            is_staff=True,
        ).count()
        self.assertEqual(summary["active_staff"], active_staff)
        self.assertEqual(summary["total_pending_reports"], 3)
        self.assertEqual(
            summary["total_stale_pending_reports"],
            1,
        )
        self.assertEqual(
            summary["missing_staff_alerts"],
            active_staff * 2,
        )
        self.assertTrue(summary["has_issues"])
        self.assertEqual(
            report["queues"]["post_reports"][
                "missing_staff_alerts"
            ],
            0,
        )

    def test_fail_on_issues_supports_monitoring(self):
        self.create_pending_reports()

        with self.assertRaises(CommandError):
            call_command(
                "audit_moderation_queue",
                stale_hours=24,
                fail_on_issues=True,
            )

    def test_healthy_empty_queue_passes_strict_mode(self):
        call_command(
            "audit_moderation_queue",
            stale_hours=24,
            fail_on_issues=True,
        )
