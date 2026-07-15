from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from matches.models import MutualMatch
from profiles.models import Profile, UserBlock

from .models import ChatMessage, ChatThread


User = get_user_model()


@override_settings(
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher"
    ]
)
class ChatSafetyTests(TestCase):
    def create_user(self, username):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="StrongPass123!",
        )
        profile = Profile.objects.get(user=user)
        profile.display_name = username.title()
        profile.age = 25
        profile.gender = Profile.GENDER_MAN
        profile.interested_in = (
            Profile.INTERESTED_IN_EVERYONE
        )
        profile.profile_visible = True
        profile.hidden_by_moderation = False
        profile.save()
        return user

    def setUp(self):
        self.user_a = self.create_user("user_a")
        self.user_b = self.create_user("user_b")
        self.outsider = self.create_user("outsider")

    def json_post(self, url, data=None):
        return self.client.post(
            url,
            data or {},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

    def test_thread_pair_is_canonical_and_idempotent(self):
        first = ChatThread.get_or_create_between(
            self.user_a,
            self.user_b,
        )
        second = ChatThread.get_or_create_between(
            self.user_b,
            self.user_a,
        )

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ChatThread.objects.count(), 1)
        self.assertLess(
            first.user_one_id,
            first.user_two_id,
        )

    def test_self_thread_is_rejected(self):
        with self.assertRaises(ValueError):
            ChatThread.get_or_create_between(
                self.user_a,
                self.user_a,
            )

    def test_start_chat_requires_mutual_match(self):
        self.client.force_login(self.user_a)

        response = self.client.get(
            reverse(
                "chat:start_chat",
                args=[self.user_b.id],
            )
        )

        self.assertRedirects(
            response,
            reverse("matches:discover"),
            fetch_redirect_response=False,
        )
        self.assertFalse(ChatThread.objects.exists())

    def test_matched_users_can_start_one_chat(self):
        MutualMatch.create_safe(
            self.user_a,
            self.user_b,
        )
        self.client.force_login(self.user_a)

        first = self.client.get(
            reverse(
                "chat:start_chat",
                args=[self.user_b.id],
            )
        )
        second = self.client.get(
            reverse(
                "chat:start_chat",
                args=[self.user_b.id],
            )
        )

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(ChatThread.objects.count(), 1)

    def test_outsider_cannot_open_chat_room(self):
        thread = ChatThread.get_or_create_between(
            self.user_a,
            self.user_b,
        )
        self.client.force_login(self.outsider)

        response = self.client.get(
            reverse(
                "chat:chat_room",
                args=[thread.id],
            )
        )

        self.assertRedirects(
            response,
            reverse("chat:chat_home"),
            fetch_redirect_response=False,
        )

    def test_clear_for_me_preserves_shared_data(self):
        thread = ChatThread.get_or_create_between(
            self.user_a,
            self.user_b,
        )
        message = ChatMessage.objects.create(
            thread=thread,
            sender=self.user_a,
            text="Preserve me",
        )
        self.client.force_login(self.user_a)

        response = self.json_post(
            reverse(
                "chat:clear_chat_for_me",
                args=[thread.id],
            )
        )

        self.assertEqual(response.status_code, 409)
        self.assertTrue(
            ChatMessage.objects.filter(id=message.id).exists()
        )
        self.assertTrue(
            ChatThread.objects.filter(id=thread.id).exists()
        )

    def test_delete_for_me_preserves_shared_thread(self):
        thread = ChatThread.get_or_create_between(
            self.user_a,
            self.user_b,
        )
        message = ChatMessage.objects.create(
            thread=thread,
            sender=self.user_a,
            text="Preserve me",
        )
        self.client.force_login(self.user_a)

        response = self.json_post(
            reverse(
                "chat:delete_chat_for_me",
                args=[thread.id],
            )
        )

        self.assertEqual(response.status_code, 409)
        self.assertTrue(
            ChatMessage.objects.filter(id=message.id).exists()
        )
        self.assertTrue(
            ChatThread.objects.filter(id=thread.id).exists()
        )

    def test_hard_delete_endpoint_is_disabled(self):
        thread = ChatThread.get_or_create_between(
            self.user_a,
            self.user_b,
        )
        self.client.force_login(self.user_a)

        response = self.json_post(
            reverse(
                "chat:delete_chat",
                args=[thread.id],
            )
        )

        self.assertEqual(response.status_code, 409)
        self.assertTrue(
            ChatThread.objects.filter(id=thread.id).exists()
        )

@override_settings(
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher"
    ]
)
class ChatMessageReliabilityTests(TestCase):
    def create_user(self, username):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="StrongPass123!",
        )
        profile = Profile.objects.get(user=user)
        profile.display_name = username.title()
        profile.age = 25
        profile.gender = Profile.GENDER_MAN
        profile.interested_in = (
            Profile.INTERESTED_IN_EVERYONE
        )
        profile.profile_visible = True
        profile.hidden_by_moderation = False
        profile.save()
        return user

    def setUp(self):
        self.sender = self.create_user("sender")
        self.recipient = self.create_user("recipient")
        self.outsider = self.create_user("outsider")
        self.thread = ChatThread.get_or_create_between(
            self.sender,
            self.recipient,
        )
        self.client.force_login(self.sender)
        self.send_url = reverse(
            "chat:send_message",
            args=[self.thread.id],
        )

    def json_post(self, data):
        return self.client.post(
            self.send_url,
            data,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

    @patch("chat.views.broadcast_message")
    @patch("chat.views.create_message_notification")
    def test_retry_with_same_client_id_creates_one_message(
        self,
        create_notification,
        broadcast,
    ):
        payload = {
            "text": "Reliable hello",
            "client_message_id": (
                "8f53dce9-5b18-4b25-a123-000000000001"
            ),
        }

        first = self.json_post(payload)
        second = self.json_post(payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(ChatMessage.objects.count(), 1)
        self.assertFalse(first.json()["duplicate"])
        self.assertTrue(second.json()["duplicate"])
        self.assertEqual(
            first.json()["message"]["id"],
            second.json()["message"]["id"],
        )
        create_notification.assert_called_once()
        broadcast.assert_called_once()

    def test_invalid_client_id_is_rejected(self):
        response = self.json_post(
            {
                "text": "Invalid request ID",
                "client_message_id": "bad id!",
            }
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(ChatMessage.objects.exists())

    def test_message_longer_than_limit_is_rejected(self):
        response = self.json_post(
            {
                "text": "x" * 1201,
                "client_message_id": (
                    "8f53dce9-5b18-4b25-a123-000000000002"
                ),
            }
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(ChatMessage.objects.exists())

    def test_non_participant_cannot_send(self):
        self.client.force_login(self.outsider)

        response = self.json_post(
            {
                "text": "Unauthorized",
                "client_message_id": (
                    "8f53dce9-5b18-4b25-a123-000000000003"
                ),
            }
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ChatMessage.objects.exists())

    def test_blocked_users_cannot_send(self):
        UserBlock.objects.create(
            blocker=self.recipient,
            blocked=self.sender,
        )

        response = self.json_post(
            {
                "text": "Blocked",
                "client_message_id": (
                    "8f53dce9-5b18-4b25-a123-000000000004"
                ),
            }
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ChatMessage.objects.exists())

    def test_reply_must_belong_to_same_thread(self):
        other_thread = ChatThread.get_or_create_between(
            self.sender,
            self.outsider,
        )
        unrelated = ChatMessage.objects.create(
            thread=other_thread,
            sender=self.sender,
            text="Other thread",
        )

        response = self.json_post(
            {
                "text": "Invalid reply",
                "reply_to_id": unrelated.id,
                "client_message_id": (
                    "8f53dce9-5b18-4b25-a123-000000000005"
                ),
            }
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ChatMessage.objects.count(), 1)

    @patch("chat.views.broadcast_message")
    @patch("chat.views.create_message_notification")
    def test_valid_reply_is_saved(
        self,
        _create_notification,
        _broadcast,
    ):
        original = ChatMessage.objects.create(
            thread=self.thread,
            sender=self.recipient,
            text="Original",
        )

        response = self.json_post(
            {
                "text": "Reply",
                "reply_to_id": original.id,
                "client_message_id": (
                    "8f53dce9-5b18-4b25-a123-000000000006"
                ),
            }
        )

        self.assertEqual(response.status_code, 200)
        reply = ChatMessage.objects.exclude(id=original.id).get()
        self.assertEqual(reply.reply_to_id, original.id)

    @patch(
        "chat.views.ChatAttachment.objects.create",
        side_effect=RuntimeError("storage failed"),
    )
    def test_attachment_failure_rolls_back_message(
        self,
        _create_attachment,
    ):
        image = SimpleUploadedFile(
            "photo.jpg",
            b"test-image-data",
            content_type="image/jpeg",
        )

        response = self.json_post(
            {
                "text": "Photo",
                "image": image,
                "client_message_id": (
                    "8f53dce9-5b18-4b25-a123-000000000007"
                ),
            }
        )

        self.assertEqual(response.status_code, 500)
        self.assertFalse(ChatMessage.objects.exists())

