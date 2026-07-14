import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import PushSubscription


@override_settings(
    VAPID_PUBLIC_KEY="test-public-key",
    VAPID_PRIVATE_KEY="test-private-key",
)
class PushSubscriptionViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="push-user",
            password="test-password-123",
        )
        self.client.force_login(self.user)

    def test_config_reports_push_available(self):
        response = self.client.get(reverse("notifications:push_config"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["enabled"])
        self.assertEqual(response.json()["public_key"], "test-public-key")

    def test_subscribe_saves_current_device(self):
        response = self.client.post(
            reverse("notifications:push_subscribe"),
            data=json.dumps(
                {
                    "endpoint": "https://push.example.test/subscription/123",
                    "keys": {"p256dh": "device-key", "auth": "auth-key"},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        subscription = PushSubscription.objects.get()
        self.assertEqual(subscription.user, self.user)
        self.assertTrue(subscription.enabled)

    def test_subscribe_rejects_non_https_endpoint(self):
        response = self.client.post(
            reverse("notifications:push_subscribe"),
            data=json.dumps(
                {
                    "endpoint": "http://push.example.test/subscription/123",
                    "keys": {"p256dh": "device-key", "auth": "auth-key"},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(PushSubscription.objects.exists())

    def test_unsubscribe_removes_only_current_users_device(self):
        endpoint = "https://push.example.test/subscription/123"
        PushSubscription.objects.create(
            user=self.user,
            endpoint=endpoint,
            p256dh="device-key",
            auth="auth-key",
        )

        response = self.client.post(
            reverse("notifications:push_unsubscribe"),
            data=json.dumps({"endpoint": endpoint}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(PushSubscription.objects.exists())
