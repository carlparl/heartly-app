from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from matches.models import MutualMatch
from profiles.models import Profile

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
