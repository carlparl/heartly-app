from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from notifications.models import Notification
from profiles.models import Profile, UserBlock

from .models import (
    CallSession,
    ChatMessage,
    ChatReport,
    ChatThread,
)


User = get_user_model()


@override_settings(
    HEARTLY_ENFORCE_ADULT_IDENTITY=False,
    HEARTLY_REQUIRE_VERIFIED_EMAIL=False,
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher"
    ],
)
class ChatModerationHardeningTests(TestCase):
    def create_user(self, username):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="StrongPass123!",
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
        self.reporter = self.create_user("chat_reporter")
        self.reported = self.create_user("chat_reported")
        self.thread = ChatThread.get_or_create_between(
            self.reporter,
            self.reported,
        )
        self.client.force_login(self.reporter)

    @patch("chat.views.notify_chat_report")
    def test_chat_report_is_saved_and_notified_once(self, notify):
        url = reverse(
            "chat:report_thread_user",
            args=[self.thread.id],
        )
        headers = {
            "HTTP_X_REQUESTED_WITH": "XMLHttpRequest",
            "HTTP_ACCEPT": "application/json",
        }

        first = self.client.post(
            url,
            {"reason": ChatReport.REASON_SPAM},
            **headers,
        )
        second = self.client.post(url, {}, **headers)

        self.assertTrue(first.json()["created"])
        self.assertFalse(second.json()["created"])
        self.assertEqual(ChatReport.objects.count(), 1)
        notify.assert_called_once()

    def test_block_from_chat_resolves_notifications(self):
        notification = Notification.objects.create(
            recipient=self.reporter,
            actor=self.reported,
            notification_type=Notification.TYPE_MESSAGE,
            title="New message",
        )

        response = self.client.post(
            reverse(
                "chat:block_thread_user",
                args=[self.thread.id],
            )
        )

        self.assertEqual(response.status_code, 302)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertTrue(notification.is_resolved)

    def test_blocked_member_cannot_open_call_or_attachment(self):
        call = CallSession.objects.create(
            thread=self.thread,
            caller=self.reporter,
            receiver=self.reported,
            call_type=CallSession.CALL_AUDIO,
        )
        message = ChatMessage.objects.create(
            thread=self.thread,
            sender=self.reported,
            text="Attachment access test",
        )
        UserBlock.objects.create(
            blocker=self.reporter,
            blocked=self.reported,
        )

        call_response = self.client.get(
            reverse("chat:call_room", args=[call.id])
        )
        status_response = self.client.get(
            reverse("chat:call_status", args=[call.id])
        )
        attachment_response = self.client.get(
            reverse(
                "chat:open_message_attachment",
                args=[message.id],
            )
        )

        self.assertRedirects(
            call_response,
            reverse("chat:chat_home"),
            fetch_redirect_response=False,
        )
        self.assertEqual(status_response.status_code, 403)
        self.assertRedirects(
            attachment_response,
            reverse("chat:chat_home"),
            fetch_redirect_response=False,
        )
