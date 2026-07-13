from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Notification
from .services import notify, notify_once
from .utils import notification_snapshot


class NotificationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.recipient = User.objects.create_user(
            username="recipient",
            email="recipient@example.com",
            password="test-pass-123",
        )
        self.actor = User.objects.create_user(
            username="actor",
            email="actor@example.com",
            password="test-pass-123",
        )
        self.client.force_login(self.recipient)

    def test_notify_creates_unread_notification(self):
        item = notify(
            recipient=self.recipient,
            actor=self.actor,
            title="New like",
            notification_type=Notification.TYPE_LIKE,
        )
        self.assertIsNotNone(item)
        self.assertFalse(item.is_read)

    def test_notify_ignores_self_notification(self):
        item = notify(
            recipient=self.recipient,
            actor=self.recipient,
            title="Self alert",
        )
        self.assertIsNone(item)

    def test_notify_once_updates_existing_notification(self):
        first = notify_once(
            recipient=self.recipient,
            actor=self.actor,
            title="First",
            notification_type=Notification.TYPE_LIKE,
            related_object_type="post",
            related_object_id=4,
        )
        second = notify_once(
            recipient=self.recipient,
            actor=self.actor,
            title="Updated",
            notification_type=Notification.TYPE_LIKE,
            related_object_type="post",
            related_object_id=4,
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            Notification.objects.filter(recipient=self.recipient).count(),
            1,
        )

    def test_snapshot_contains_unread_count(self):
        notify(recipient=self.recipient, actor=self.actor, title="Alert")
        snapshot = notification_snapshot(self.recipient)
        self.assertEqual(snapshot["unread_count"], 1)
        self.assertEqual(len(snapshot["notifications"]), 1)

    def test_snapshot_endpoint(self):
        notify(recipient=self.recipient, actor=self.actor, title="Alert")
        response = self.client.get(reverse("notifications:snapshot"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["unread_count"], 1)

    def test_mark_all_read_ajax(self):
        notify(recipient=self.recipient, actor=self.actor, title="Alert")
        response = self.client.post(
            reverse("notifications:mark_notifications_read"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Notification.objects.filter(
                recipient=self.recipient,
                is_read=False,
            ).exists()
        )
