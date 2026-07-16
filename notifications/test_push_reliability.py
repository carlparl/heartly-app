from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from notifications.models import Notification, PushSubscription
from notifications.push import (
    notification_push_payload,
    notification_ttl,
    send_notification_push,
)


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class FakeWebPushException(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.response = FakeResponse(status_code)


class PushReliabilityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="push-user",
            email="push@example.com",
            password="Pass12345!",
        )
        self.notification = Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.TYPE_MESSAGE,
            title="New message",
            message="Someone sent you a message.",
            url="/chat/1/",
            related_object_type="chat.chatmessage",
            related_object_id=10,
        )
        self.subscription = PushSubscription.objects.create(
            user=self.user,
            endpoint="https://push.example.com/endpoint",
            p256dh="p256dh",
            auth="auth",
            enabled=True,
        )

    def test_payload_uses_notification_open_route(self):
        payload = notification_push_payload(
            self.notification
        )

        self.assertEqual(
            payload["url"],
            reverse(
                "notifications:open_notification",
                args=[self.notification.id],
            ),
        )
        self.assertEqual(
            payload["notification_id"],
            self.notification.id,
        )
        self.assertEqual(
            payload["notification_type"],
            Notification.TYPE_MESSAGE,
        )
        self.assertGreater(
            notification_ttl(self.notification),
            300,
        )

    @override_settings(
        VAPID_PUBLIC_KEY="public",
        VAPID_PRIVATE_KEY="private",
        VAPID_SUBJECT="mailto:test@example.com",
        HEARTLY_PUSH_RETRY_ATTEMPTS=2,
        HEARTLY_PUSH_RETRY_DELAY_SECONDS=0,
    )
    @patch(
        "notifications.push.WebPushException",
        FakeWebPushException,
    )
    @patch("notifications.push.time.sleep")
    @patch("notifications.push.webpush")
    def test_transient_failure_is_retried(
        self,
        mocked_webpush,
        mocked_sleep,
    ):
        mocked_webpush.side_effect = [
            FakeWebPushException(503),
            None,
        ]

        delivered = send_notification_push(
            self.notification.id
        )

        self.assertEqual(delivered, 1)
        self.assertEqual(mocked_webpush.call_count, 2)
        mocked_sleep.assert_called_once()
        call_kwargs = mocked_webpush.call_args.kwargs
        self.assertEqual(
            call_kwargs["headers"]["Urgency"],
            "high",
        )
        self.assertIn(
            "Topic",
            call_kwargs["headers"],
        )

    @override_settings(
        VAPID_PUBLIC_KEY="public",
        VAPID_PRIVATE_KEY="private",
        VAPID_SUBJECT="mailto:test@example.com",
        HEARTLY_PUSH_RETRY_ATTEMPTS=2,
        HEARTLY_PUSH_RETRY_DELAY_SECONDS=0,
    )
    @patch(
        "notifications.push.WebPushException",
        FakeWebPushException,
    )
    @patch("notifications.push.webpush")
    def test_expired_subscription_is_deleted(
        self,
        mocked_webpush,
    ):
        mocked_webpush.side_effect = (
            FakeWebPushException(410)
        )

        delivered = send_notification_push(
            self.notification.id
        )

        self.assertEqual(delivered, 0)
        self.assertFalse(
            PushSubscription.objects.filter(
                pk=self.subscription.pk,
            ).exists()
        )
        self.assertEqual(mocked_webpush.call_count, 1)

    @override_settings(
        VAPID_PUBLIC_KEY="public",
        VAPID_PRIVATE_KEY="private",
        VAPID_SUBJECT="mailto:test@example.com",
    )
    def test_push_config_reports_active_subscription(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("notifications:push_config")
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["enabled"])
        self.assertTrue(payload["has_subscription"])
        self.assertEqual(
            payload["subscription_count"],
            1,
        )
