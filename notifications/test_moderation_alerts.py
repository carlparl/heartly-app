from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from chat.models import ChatReport, ChatThread
from feed.models import Post, PostReport
from profiles.models import Profile, ProfileReport

from .activity import notify_profile_report
from .models import Notification


User = get_user_model()


@override_settings(
    HEARTLY_ENFORCE_ADULT_IDENTITY=False,
    HEARTLY_REQUIRE_VERIFIED_EMAIL=False,
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher"
    ],
)
class ModerationAlertDeliveryTests(TestCase):
    def create_user(self, username, **extra):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="StrongPass123!",
            **extra,
        )
        profile = Profile.objects.get(user=user)
        profile.profile_visible = True
        profile.hidden_by_moderation = False
        profile.save(
            update_fields=[
                "profile_visible",
                "hidden_by_moderation",
                "updated_at",
            ]
        )
        return user

    def setUp(self):
        self.staff = self.create_user(
            "alert_staff",
            is_staff=True,
        )
        self.inactive_staff = self.create_user(
            "inactive_alert_staff",
            is_staff=True,
            is_active=False,
        )
        self.reporter = self.create_user("alert_reporter")
        self.target = self.create_user(
            "alert_target",
            is_staff=True,
        )
        self.client.force_login(self.reporter)

    def staff_alerts(self, related_object_type, object_id):
        return Notification.objects.filter(
            recipient=self.staff,
            notification_type=Notification.TYPE_REPORT,
            related_object_type=related_object_type,
            related_object_id=object_id,
        )

    def test_profile_report_route_alerts_active_staff_once(self):
        url = reverse(
            "profiles:report_profile",
            args=[self.target.id],
        )
        response = self.client.post(
            url,
            {"reason": ProfileReport.REASON_SPAM},
        )
        self.assertEqual(response.status_code, 302)
        report = ProfileReport.objects.get(
            reporter=self.reporter,
            reported_user=self.target,
        )
        alerts = self.staff_alerts(
            "profiles.profilereport",
            report.id,
        )
        self.assertEqual(alerts.count(), 1)
        self.assertEqual(
            alerts.get().url,
            reverse(
                "admin:profiles_profilereport_change",
                args=[report.id],
            ),
        )
        self.assertFalse(
            Notification.objects.filter(
                recipient=self.inactive_staff,
                related_object_type=(
                    "profiles.profilereport"
                ),
                related_object_id=report.id,
            ).exists()
        )
        self.assertFalse(
            Notification.objects.filter(
                recipient=self.target,
                related_object_type=(
                    "profiles.profilereport"
                ),
                related_object_id=report.id,
            ).exists()
        )

        self.client.post(
            url,
            {"reason": ProfileReport.REASON_SPAM},
        )
        self.assertEqual(alerts.count(), 1)

    def test_post_report_route_alerts_active_staff_once(self):
        post = Post.objects.create(
            author=self.target,
            content="Report alert marker",
        )
        url = reverse("feed:report_post", args=[post.id])

        response = self.client.post(
            url,
            {"reason": PostReport.REASON_SPAM},
        )
        self.assertEqual(response.status_code, 302)
        report = PostReport.objects.get(
            post=post,
            reporter=self.reporter,
        )
        alerts = self.staff_alerts(
            "feed.postreport",
            report.id,
        )
        self.assertEqual(alerts.count(), 1)
        self.assertEqual(
            alerts.get().url,
            reverse(
                "admin:feed_postreport_change",
                args=[report.id],
            ),
        )

        self.client.post(
            url,
            {"reason": PostReport.REASON_SPAM},
        )
        self.assertEqual(alerts.count(), 1)

    def test_chat_report_route_keeps_admin_deep_link(self):
        thread = ChatThread.get_or_create_between(
            self.reporter,
            self.target,
        )
        response = self.client.post(
            reverse(
                "chat:report_thread_user",
                args=[thread.id],
            ),
            {"reason": ChatReport.REASON_SPAM},
        )
        self.assertEqual(response.status_code, 302)
        report = ChatReport.objects.get(
            thread=thread,
            reporter=self.reporter,
        )
        alert = self.staff_alerts(
            "chat.chatreport",
            report.id,
        ).get()
        self.assertEqual(
            alert.url,
            reverse(
                "admin:chat_chatreport_change",
                args=[report.id],
            ),
        )

    def test_alert_failure_does_not_break_report_delivery(self):
        report = ProfileReport.objects.create(
            reporter=self.reporter,
            reported_user=self.target,
            reason=ProfileReport.REASON_SPAM,
        )

        with self.assertLogs(
            "notifications.activity",
            level="ERROR",
        ):
            with patch(
                "notifications.activity.notify_once",
                side_effect=RuntimeError("delivery failed"),
            ):
                self.assertEqual(
                    notify_profile_report(report),
                    [],
                )

        self.assertTrue(
            ProfileReport.objects.filter(pk=report.pk).exists()
        )
