from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from notifications.activity import notify_chat_report
from profiles.models import ModerationAction, Profile

from .admin import ChatReportAdmin
from .models import ChatReport, ChatThread


User = get_user_model()


@override_settings(
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher"
    ]
)
class ChatModerationWorkflowTests(TestCase):
    def create_user(self, username, **extra):
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="StrongPass123!",
            **extra,
        )

    def setUp(self):
        self.moderator = self.create_user(
            "chat_moderator",
            is_staff=True,
            is_superuser=True,
        )
        self.reporter = self.create_user("chat_workflow_reporter")
        self.reported = self.create_user("chat_workflow_reported")
        self.thread = ChatThread.get_or_create_between(
            self.reporter,
            self.reported,
        )
        self.report = ChatReport.objects.create(
            thread=self.thread,
            reporter=self.reporter,
            reported_user=self.reported,
            reason=ChatReport.REASON_UNSAFE,
            moderator_note="Reviewed chat safety context.",
        )
        self.request = RequestFactory().post("/admin/")
        self.request.user = self.moderator
        self.model_admin = ChatReportAdmin(
            ChatReport,
            admin.site,
        )

    def test_chat_report_review_is_audited(self):
        notification = notify_chat_report(self.report)[0]
        self.model_admin.mark_reviewed(
            self.request,
            ChatReport.objects.filter(pk=self.report.pk),
        )

        self.report.refresh_from_db()
        self.assertTrue(self.report.reviewed)
        self.assertEqual(
            self.report.status,
            ChatReport.STATUS_REVIEWED,
        )
        self.assertEqual(
            self.report.reviewed_by,
            self.moderator,
        )
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertTrue(notification.is_resolved)
        action = ModerationAction.objects.get(
            source_type=ModerationAction.SOURCE_CHAT_REPORT,
            source_object_id=self.report.id,
        )
        self.assertEqual(
            action.action,
            ModerationAction.ACTION_REPORT_REVIEWED,
        )

    def test_chat_report_can_hide_and_restore_profile(self):
        queryset = ChatReport.objects.filter(pk=self.report.pk)

        self.model_admin.hide_reported_users(
            self.request,
            queryset,
        )
        profile = Profile.objects.get(user=self.reported)
        self.report.refresh_from_db()

        self.assertTrue(profile.hidden_by_moderation)
        self.assertEqual(
            self.report.status,
            ChatReport.STATUS_ACTIONED,
        )
        self.assertTrue(
            ModerationAction.objects.filter(
                action=(
                    ModerationAction.ACTION_PROFILE_HIDDEN
                ),
                source_type=(
                    ModerationAction.SOURCE_CHAT_REPORT
                ),
                source_object_id=self.report.id,
            ).exists()
        )

        self.model_admin.restore_reported_users(
            self.request,
            queryset,
        )
        profile.refresh_from_db()
        self.assertFalse(profile.hidden_by_moderation)
        self.assertTrue(
            ModerationAction.objects.filter(
                action=(
                    ModerationAction.ACTION_PROFILE_RESTORED
                ),
                source_object_id=self.report.id,
            ).exists()
        )
