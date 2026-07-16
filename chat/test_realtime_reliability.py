from django.contrib.auth import get_user_model
from django.test import TestCase

from notifications.models import Notification

from .models import ChatMessage, ChatThread
from .realtime import mark_message_read_for_user, mark_thread_read_for_user


class ChatRealtimeReliabilityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.sender = User.objects.create_user(
            username="realtime-sender",
            email="realtime-sender@example.com",
            password="Pass12345!",
        )
        self.recipient = User.objects.create_user(
            username="realtime-recipient",
            email="realtime-recipient@example.com",
            password="Pass12345!",
        )
        self.thread = ChatThread.get_or_create_between(self.sender, self.recipient)

    def make_notification(self, message):
        return Notification.objects.create(
            recipient=self.recipient,
            actor=self.sender,
            notification_type=Notification.TYPE_MESSAGE,
            title="New message",
            message="A message arrived.",
            url=f"/chat/{self.thread.id}/",
            related_object_type="chat.chatmessage",
            related_object_id=message.id,
        )

    def test_one_live_message_and_notification_become_read(self):
        message = ChatMessage.objects.create(
            thread=self.thread,
            sender=self.sender,
            text="Live message",
        )
        notification = self.make_notification(message)

        changed_id = mark_message_read_for_user(
            self.thread.id,
            message.id,
            self.recipient,
        )

        self.assertEqual(changed_id, message.id)
        message.refresh_from_db()
        notification.refresh_from_db()
        self.assertTrue(message.is_read)
        self.assertTrue(notification.is_read)

    def test_opening_thread_marks_only_incoming_messages(self):
        first = ChatMessage.objects.create(
            thread=self.thread,
            sender=self.sender,
            text="First incoming",
        )
        second = ChatMessage.objects.create(
            thread=self.thread,
            sender=self.sender,
            text="Second incoming",
        )
        own_message = ChatMessage.objects.create(
            thread=self.thread,
            sender=self.recipient,
            text="My outgoing message",
        )
        first_notification = self.make_notification(first)
        second_notification = self.make_notification(second)

        changed_ids = mark_thread_read_for_user(self.thread.id, self.recipient)

        self.assertEqual(set(changed_ids), {first.id, second.id})
        first.refresh_from_db()
        second.refresh_from_db()
        own_message.refresh_from_db()
        first_notification.refresh_from_db()
        second_notification.refresh_from_db()
        self.assertTrue(first.is_read)
        self.assertTrue(second.is_read)
        self.assertFalse(own_message.is_read)
        self.assertTrue(first_notification.is_read)
        self.assertTrue(second_notification.is_read)

    def test_outsider_cannot_mark_message_read(self):
        User = get_user_model()
        outsider = User.objects.create_user(
            username="realtime-outsider",
            email="realtime-outsider@example.com",
            password="Pass12345!",
        )
        message = ChatMessage.objects.create(
            thread=self.thread,
            sender=self.sender,
            text="Private",
        )

        changed_id = mark_message_read_for_user(
            self.thread.id,
            message.id,
            outsider,
        )

        self.assertIsNone(changed_id)
        message.refresh_from_db()
        self.assertFalse(message.is_read)
