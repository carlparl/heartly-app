from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from notifications.models import Notification

from .models import ProfileReport, UserBlock


User = get_user_model()


@override_settings(
    HEARTLY_ENFORCE_ADULT_IDENTITY=False,
    HEARTLY_REQUIRE_VERIFIED_EMAIL=False,
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher"
    ],
)
class ProfileModerationHardeningTests(TestCase):
    def setUp(self):
        self.viewer = User.objects.create_user(
            username="profile_viewer",
            email="profile-viewer@example.com",
            password="StrongPass123!",
        )
        self.target = User.objects.create_user(
            username="profile_target",
            email="profile-target@example.com",
            password="StrongPass123!",
        )
        self.client.force_login(self.viewer)

    def test_block_resolves_member_notifications(self):
        notification = Notification.objects.create(
            recipient=self.viewer,
            actor=self.target,
            notification_type=Notification.TYPE_MESSAGE,
            title="New message",
        )

        response = self.client.post(
            reverse(
                "profiles:block_user",
                args=[self.target.id],
            )
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            UserBlock.objects.filter(
                blocker=self.viewer,
                blocked=self.target,
            ).exists()
        )
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertTrue(notification.is_resolved)

    def test_profile_report_normalizes_reason_and_limits_details(self):
        self.client.post(
            reverse(
                "profiles:report_profile",
                args=[self.target.id],
            ),
            {
                "reason": "not-a-real-reason",
                "details": "x" * 2500,
            },
        )

        report = ProfileReport.objects.get(
            reporter=self.viewer,
            reported_user=self.target,
        )
        self.assertEqual(
            report.reason,
            ProfileReport.REASON_OTHER,
        )
        self.assertEqual(len(report.details), 2000)
