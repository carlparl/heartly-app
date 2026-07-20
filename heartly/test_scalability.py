from datetime import date

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from chat.models import ChatMessage, ChatThread
from notifications.models import Notification
from profiles.identity import age_from_date_of_birth
from profiles.models import Profile


User = get_user_model()


@override_settings(
    HEARTLY_ENFORCE_ADULT_IDENTITY=False,
    HEARTLY_REQUIRE_VERIFIED_EMAIL=False,
)
class BoundedCollectionTests(TestCase):
    def create_user(self, username, *, gender="male", interested_in="female"):
        birth_date = date(1990, 1, 1)
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="StrongPass123!",
            date_of_birth=birth_date,
            gender=gender,
            interested_in=interested_in,
        )
        profile, _created = Profile.objects.get_or_create(user=user)
        profile.display_name = username.replace("-", " ").title()
        profile.age = age_from_date_of_birth(birth_date)
        profile.gender = (
            Profile.GENDER_MAN
            if gender == "male"
            else Profile.GENDER_WOMAN
        )
        profile.interested_in = (
            Profile.INTERESTED_IN_WOMEN
            if interested_in == "female"
            else Profile.INTERESTED_IN_MEN
        )
        profile.connection_goal = Profile.CONNECTION_DATING
        profile.profile_visible = True
        profile.hidden_by_moderation = False
        profile.save()
        return user

    @override_settings(HEARTLY_NOTIFICATION_PAGE_SIZE=2)
    def test_notifications_are_paginated(self):
        recipient = self.create_user("notification-owner")
        for index in range(5):
            Notification.objects.create(
                recipient=recipient,
                title=f"Notification {index}",
            )
        self.client.force_login(recipient)

        response = self.client.get(
            reverse("notifications:notifications_home"),
            {"page": 2},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["notifications"]), 2)
        self.assertEqual(response.context["page_obj"].number, 2)

    @override_settings(HEARTLY_CHAT_MESSAGE_LIMIT=2)
    def test_chat_room_loads_only_recent_messages(self):
        user_a = self.create_user("history-a")
        user_b = self.create_user("history-b")
        thread = ChatThread.get_or_create_between(user_a, user_b)
        messages = [
            ChatMessage.objects.create(
                thread=thread,
                sender=user_a,
                text=f"Message {index}",
            )
            for index in range(4)
        ]
        self.client.force_login(user_a)

        response = self.client.get(
            reverse("chat:chat_room", args=[thread.id])
        )

        returned_ids = [
            item.id for item in response.context["chat_messages"]
        ]
        self.assertEqual(
            returned_ids,
            [messages[2].id, messages[3].id],
        )
        self.assertTrue(response.context["message_history_limited"])

    @override_settings(HEARTLY_CHAT_THREAD_LIMIT=20)
    def test_chat_list_queries_do_not_scale_per_thread(self):
        viewer = self.create_user("thread-viewer")
        for index in range(8):
            other = self.create_user(f"thread-other-{index}")
            thread = ChatThread.get_or_create_between(viewer, other)
            ChatMessage.objects.create(
                thread=thread,
                sender=other,
                text=f"Latest {index}",
            )
        self.client.force_login(viewer)

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(reverse("chat:chat_home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["thread_cards"]), 8)
        self.assertLessEqual(len(captured), 25)

    @override_settings(HEARTLY_DISCOVER_PAGE_SIZE=2)
    def test_discover_is_paginated(self):
        viewer = self.create_user(
            "discover-viewer",
            gender="female",
            interested_in="male",
        )
        for index in range(5):
            self.create_user(
                f"discover-target-{index}",
                gender="male",
                interested_in="female",
            )
        self.client.force_login(viewer)

        response = self.client.get(
            reverse("matches:discover"),
            {"page": 2},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["profiles"]), 2)
        self.assertEqual(response.context["page_obj"].number, 2)

    @override_settings(
        HEARTLY_DISCOVER_PAGE_SIZE=2,
        HEARTLY_DISCOVER_CANDIDATE_LIMIT=2,
    )
    def test_discover_search_filters_before_candidate_limit(self):
        viewer = self.create_user(
            "search-viewer",
            gender="female",
            interested_in="male",
        )
        expected = self.create_user(
            "unique-search-target",
            gender="male",
            interested_in="female",
        )
        for index in range(3):
            self.create_user(
                f"newer-target-{index}",
                gender="male",
                interested_in="female",
            )
        self.client.force_login(viewer)

        response = self.client.get(
            reverse("matches:discover"),
            {"q": "unique-search-target"},
        )

        returned_ids = {
            profile.user_id for profile in response.context["profiles"]
        }
        self.assertEqual(returned_ids, {expected.id})
