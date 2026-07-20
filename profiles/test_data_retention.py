import json
import tempfile
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import EmailVerificationCode
from chat.models import ChatReport, ChatThread
from feed.models import Post, PostReport
from notifications.models import Notification, PushSubscription
from profiles.models import ProfileReport


User = get_user_model()


@override_settings(
    HEARTLY_RETENTION_EMAIL_CODE_DAYS=2,
    HEARTLY_RETENTION_RESOLVED_NOTIFICATION_DAYS=30,
    HEARTLY_RETENTION_DISABLED_PUSH_DAYS=7,
)
class DataRetentionTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.user = User.objects.create_user(
            username="retention-user",
            email="retention-user@example.com",
            password="StrongPass123!",
        )
        self.other = User.objects.create_user(
            username="retention-other",
            email="retention-other@example.com",
            password="StrongPass123!",
        )

        self.old_code = EmailVerificationCode.objects.create(
            user=self.user,
            email=self.user.email,
            code_hash="old-code",
            expires_at=self.now - timedelta(days=10),
            used_at=self.now - timedelta(days=10),
        )
        EmailVerificationCode.objects.filter(
            pk=self.old_code.pk
        ).update(created_at=self.now - timedelta(days=10))
        self.recent_code = EmailVerificationCode.objects.create(
            user=self.user,
            email=self.user.email,
            code_hash="recent-code",
            expires_at=self.now + timedelta(minutes=10),
        )

        self.old_notification = Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.TYPE_SYSTEM,
            title="Resolved old notification",
            is_read=True,
            is_resolved=True,
        )
        Notification.objects.filter(
            pk=self.old_notification.pk
        ).update(updated_at=self.now - timedelta(days=40))
        self.recent_notification = Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.TYPE_SYSTEM,
            title="Recent notification",
            is_read=True,
            is_resolved=True,
        )

        self.old_push = PushSubscription.objects.create(
            user=self.user,
            endpoint="https://push.example/old",
            p256dh="old-key",
            auth="old-auth",
            enabled=False,
        )
        PushSubscription.objects.filter(
            pk=self.old_push.pk
        ).update(updated_at=self.now - timedelta(days=10))
        self.recent_push = PushSubscription.objects.create(
            user=self.user,
            endpoint="https://push.example/recent",
            p256dh="recent-key",
            auth="recent-auth",
            enabled=False,
        )

        Session.objects.create(
            session_key="expired-retention-session",
            session_data="e30:1test:invalid",
            expire_date=self.now - timedelta(days=1),
        )

        ProfileReport.objects.create(
            reported_user=self.other,
            reporter=self.user,
            reason=ProfileReport.REASON_OTHER,
            evidence_snapshot={"schema_version": 1},
        )
        post = Post.objects.create(
            author=self.other,
            content="Preserved report target",
        )
        PostReport.objects.create(
            post=post,
            reporter=self.user,
            evidence_snapshot={"schema_version": 1},
        )
        thread = ChatThread.get_or_create_between(
            self.user,
            self.other,
        )
        ChatReport.objects.create(
            thread=thread,
            reporter=self.user,
            reported_user=self.other,
            reason=ChatReport.REASON_OTHER,
            evidence_snapshot={"schema_version": 1},
        )

    def test_audit_is_read_only_and_aggregate(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "retention.json"
            call_command(
                "audit_data_retention",
                output=str(output),
            )
            report = json.loads(output.read_text("utf-8"))

        self.assertTrue(report["read_only"])
        self.assertEqual(report["due"]["expired_email_codes"], 1)
        self.assertEqual(report["due"]["resolved_notifications"], 1)
        self.assertEqual(
            report["due"]["disabled_push_subscriptions"],
            1,
        )
        self.assertEqual(report["due"]["expired_sessions"], 1)
        self.assertTrue(
            EmailVerificationCode.objects.filter(
                pk=self.old_code.pk
            ).exists()
        )

    def test_cleanup_dry_run_does_not_delete(self):
        call_command("prune_expired_operational_data")

        self.assertTrue(
            EmailVerificationCode.objects.filter(
                pk=self.old_code.pk
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                pk=self.old_notification.pk
            ).exists()
        )
        self.assertTrue(
            PushSubscription.objects.filter(
                pk=self.old_push.pk
            ).exists()
        )

    def test_apply_deletes_only_due_operational_rows(self):
        call_command(
            "prune_expired_operational_data",
            apply=True,
        )

        self.assertFalse(
            EmailVerificationCode.objects.filter(
                pk=self.old_code.pk
            ).exists()
        )
        self.assertFalse(
            Notification.objects.filter(
                pk=self.old_notification.pk
            ).exists()
        )
        self.assertFalse(
            PushSubscription.objects.filter(
                pk=self.old_push.pk
            ).exists()
        )
        self.assertFalse(
            Session.objects.filter(
                session_key="expired-retention-session"
            ).exists()
        )
        self.assertTrue(
            EmailVerificationCode.objects.filter(
                pk=self.recent_code.pk
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                pk=self.recent_notification.pk
            ).exists()
        )
        self.assertTrue(
            PushSubscription.objects.filter(
                pk=self.recent_push.pk
            ).exists()
        )
        self.assertEqual(ProfileReport.objects.count(), 1)
        self.assertEqual(PostReport.objects.count(), 1)
        self.assertEqual(ChatReport.objects.count(), 1)
