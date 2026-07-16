import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from notifications.models import (
    Notification,
    PushSubscription,
)
from notifications.push import (
    notification_push_payload,
    notification_topic,
)


class CallAlertClientContractTests(SimpleTestCase):
    def read_file(self, relative_path):
        return (
            Path(settings.BASE_DIR) / relative_path
        ).read_text(encoding="utf-8")

    def test_legacy_call_popup_is_removed(self):
        source = self.read_file(
            "templates/heartly/base.html"
        )

        self.assertNotIn(
            'id="globalIncomingCall"',
            source,
        )
        self.assertNotIn(
            'data.type === "incoming_call"',
            source,
        )
        self.assertIn(
            '["call", "missed_call"]',
            source,
        )

    def test_primary_call_banner_deduplicates_call_id(self):
        source = self.read_file(
            "static/js/heartly-global-calls.js"
        )

        self.assertIn(
            "sameIncomingCallVisible",
            source,
        )
        self.assertIn(
            "activeCallMatches(payload.call_id)",
            source,
        )

    def test_push_client_sends_installation_identity(self):
        source = self.read_file(
            "static/js/heartly-push.js"
        )

        self.assertIn(
            "heartlyPushInstallationId",
            source,
        )
        self.assertIn(
            "installation_id",
            source,
        )


class CallPushDedupTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="alert_receiver",
            email="alert_receiver@example.com",
            password="Pass12345!",
        )
        self.actor = User.objects.create_user(
            username="alert_caller",
            email="alert_caller@example.com",
            password="Pass12345!",
        )

    def test_call_push_uses_stable_call_tag_and_topic(self):
        notification = Notification.objects.create(
            recipient=self.user,
            actor=self.actor,
            notification_type=Notification.TYPE_CALL,
            title="Incoming audio call",
            message="Someone is calling.",
            related_object_type="chat.callsession",
            related_object_id=417,
        )

        payload = notification_push_payload(
            notification
        )

        self.assertEqual(
            payload["tag"],
            "heartly-call-417",
        )
        self.assertEqual(
            notification_topic(notification),
            "heartly-call-417",
        )

    def test_new_subscription_prunes_same_device_entries(self):
        user_agent = (
            "Mozilla/5.0 (iPhone; CPU iPhone OS "
            "18_0 like Mac OS X)"
        )
        PushSubscription.objects.create(
            user=self.user,
            endpoint="https://push.example/old-one",
            p256dh="old-key-one",
            auth="old-auth-one",
            user_agent=user_agent,
        )
        PushSubscription.objects.create(
            user=self.user,
            endpoint="https://push.example/old-two",
            p256dh="old-key-two",
            auth="old-auth-two",
            user_agent=(
                user_agent
                + " | heartly-installation:oldinstall123456"
            ),
        )
        PushSubscription.objects.create(
            user=self.user,
            endpoint="https://push.example/desktop",
            p256dh="desktop-key",
            auth="desktop-auth",
            user_agent="Mozilla/5.0 (Windows NT 10.0)",
        )

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("notifications:push_subscribe"),
            data=json.dumps(
                {
                    "endpoint": (
                        "https://push.example/current"
                    ),
                    "keys": {
                        "p256dh": "current-key",
                        "auth": "current-auth",
                    },
                    "installation_id": (
                        "currentinstall1234567890"
                    ),
                }
            ),
            content_type="application/json",
            HTTP_USER_AGENT=user_agent,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            PushSubscription.objects.filter(
                user=self.user
            ).count(),
            2,
        )
        self.assertTrue(
            PushSubscription.objects.filter(
                user=self.user,
                endpoint="https://push.example/current",
            ).exists()
        )
        self.assertTrue(
            PushSubscription.objects.filter(
                user=self.user,
                endpoint="https://push.example/desktop",
            ).exists()
        )
        self.assertEqual(
            response.json()["removed_duplicates"],
            2,
        )
