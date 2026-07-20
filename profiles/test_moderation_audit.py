from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from notifications.activity import notify_profile_report

from .admin import (
    ModerationActionAdmin,
    ProfileAdmin,
    ProfileReportAdmin,
)
from .models import (
    ModerationAction,
    Profile,
    ProfileReport,
)


User = get_user_model()


@override_settings(
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher"
    ]
)
class ProfileModerationAuditTests(TestCase):
    def setUp(self):
        self.moderator = User.objects.create_superuser(
            username="profile_moderator",
            email="profile-moderator@example.com",
            password="StrongPass123!",
        )
        self.target = User.objects.create_user(
            username="profile_audit_target",
            email="profile-audit-target@example.com",
            password="StrongPass123!",
        )
        self.profile = Profile.objects.get(user=self.target)
        self.request = RequestFactory().post("/admin/")
        self.request.user = self.moderator

    def test_profile_hide_and_restore_are_audited_once(self):
        model_admin = ProfileAdmin(Profile, admin.site)
        queryset = Profile.objects.filter(pk=self.profile.pk)

        model_admin.hide_profiles(self.request, queryset)
        model_admin.hide_profiles(self.request, queryset)
        self.profile.refresh_from_db()

        self.assertTrue(self.profile.hidden_by_moderation)
        self.assertEqual(
            ModerationAction.objects.filter(
                action=(
                    ModerationAction.ACTION_PROFILE_HIDDEN
                ),
                source_type=ModerationAction.SOURCE_PROFILE,
                source_object_id=self.profile.id,
            ).count(),
            1,
        )

        model_admin.restore_profiles(self.request, queryset)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.hidden_by_moderation)
        self.assertTrue(
            ModerationAction.objects.filter(
                action=(
                    ModerationAction.ACTION_PROFILE_RESTORED
                ),
                source_object_id=self.profile.id,
            ).exists()
        )

    def test_profile_report_review_records_moderator(self):
        reporter = User.objects.create_user(
            username="profile_reporter",
            email="profile-reporter@example.com",
            password="StrongPass123!",
        )
        report = ProfileReport.objects.create(
            reported_user=self.target,
            reporter=reporter,
            reason=ProfileReport.REASON_SPAM,
            moderator_note="Checked supporting evidence.",
        )
        notification = notify_profile_report(report)[0]
        model_admin = ProfileReportAdmin(
            ProfileReport,
            admin.site,
        )

        model_admin.mark_reviewed(
            self.request,
            ProfileReport.objects.filter(pk=report.pk),
        )

        report.refresh_from_db()
        self.assertTrue(report.reviewed)
        self.assertEqual(
            report.status,
            ProfileReport.STATUS_REVIEWED,
        )
        self.assertEqual(report.reviewed_by, self.moderator)
        self.assertIsNotNone(report.reviewed_at)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertTrue(notification.is_resolved)
        action = ModerationAction.objects.get(
            source_type=(
                ModerationAction.SOURCE_PROFILE_REPORT
            ),
            source_object_id=report.id,
        )
        self.assertEqual(
            action.action,
            ModerationAction.ACTION_REPORT_REVIEWED,
        )
        self.assertEqual(
            action.note,
            "Checked supporting evidence.",
        )

    def test_audit_admin_is_append_only(self):
        model_admin = ModerationActionAdmin(
            ModerationAction,
            admin.site,
        )

        self.assertFalse(
            model_admin.has_add_permission(self.request)
        )
        self.assertFalse(
            model_admin.has_change_permission(self.request)
        )
        self.assertFalse(
            model_admin.has_delete_permission(self.request)
        )
