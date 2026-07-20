from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from profiles.models import UserBlock

from .models import Notification
from .utils import visible_notifications_for


User = get_user_model()


@override_settings(
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher"
    ]
)
class ModerationNotificationVisibilityTests(TestCase):
    def test_staff_safety_report_remains_visible(self):
        staff = User.objects.create_user(
            username="safety_staff",
            email="safety-staff@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        reporter = User.objects.create_user(
            username="private_reporter",
            email="private-reporter@example.com",
            password="StrongPass123!",
        )
        reporter.profile.profile_visible = False
        reporter.profile.hidden_by_moderation = True
        reporter.profile.save(
            update_fields=[
                "profile_visible",
                "hidden_by_moderation",
                "updated_at",
            ]
        )
        UserBlock.objects.create(
            blocker=staff,
            blocked=reporter,
        )
        report_alert = Notification.objects.create(
            recipient=staff,
            actor=reporter,
            notification_type=Notification.TYPE_REPORT,
            title="Chat report",
        )
        message_alert = Notification.objects.create(
            recipient=staff,
            actor=reporter,
            notification_type=Notification.TYPE_MESSAGE,
            title="New message",
        )

        visible_ids = set(
            visible_notifications_for(staff).values_list(
                "id",
                flat=True,
            )
        )

        self.assertIn(report_alert.id, visible_ids)
        self.assertNotIn(message_alert.id, visible_ids)
