from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from notifications.models import Notification
from profiles.models import Profile

from .models import CallSession, ChatThread
from .views import build_call_payload


@override_settings(
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher"
    ]
)
class CallReliabilityTests(TestCase):
    def create_user(self, username):
        User = get_user_model()
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="Pass12345!",
        )
        profile, _ = Profile.objects.get_or_create(
            user=user
        )
        profile.display_name = username.title()
        profile.age = 25
        profile.save()
        return user

    def setUp(self):
        self.caller = self.create_user("caller")
        self.receiver = self.create_user("receiver")
        self.outsider = self.create_user("outsider")
        self.thread = ChatThread.get_or_create_between(
            self.caller,
            self.receiver,
        )

    def create_call(self, status=CallSession.STATUS_RINGING):
        return CallSession.objects.create(
            thread=self.thread,
            caller=self.caller,
            receiver=self.receiver,
            call_type=CallSession.CALL_AUDIO,
            status=status,
        )

    @patch("chat.views.broadcast_call_event")
    def test_double_start_reuses_active_call(
        self,
        broadcast,
    ):
        self.client.force_login(self.caller)
        url = reverse(
            "chat:start_call",
            args=[self.thread.id, "audio"],
        )

        first = self.client.get(url)
        second = self.client.get(url)

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(CallSession.objects.count(), 1)
        broadcast.assert_called_once()

    @patch("chat.views.broadcast_call_event")
    def test_receiver_opening_room_accepts_call(
        self,
        broadcast,
    ):
        call = self.create_call()
        self.client.force_login(self.receiver)

        response = self.client.get(
            reverse("chat:call_room", args=[call.id])
        )

        self.assertEqual(response.status_code, 200)
        call.refresh_from_db()
        self.assertEqual(
            call.status,
            CallSession.STATUS_ACCEPTED,
        )
        self.assertIsNotNone(call.accepted_at)
        broadcast.assert_called_once_with(
            call,
            "call.accepted",
        )

    def test_status_endpoint_is_participant_only(self):
        call = self.create_call()

        self.client.force_login(self.outsider)
        denied = self.client.get(
            reverse("chat:call_status", args=[call.id])
        )
        self.assertEqual(denied.status_code, 403)

        self.client.force_login(self.caller)
        allowed = self.client.get(
            reverse("chat:call_status", args=[call.id])
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(
            allowed.json()["call"]["status"],
            CallSession.STATUS_RINGING,
        )

    @patch("chat.views.broadcast_call_event")
    def test_end_call_is_idempotent(self, broadcast):
        call = self.create_call(
            CallSession.STATUS_ACCEPTED
        )
        self.client.force_login(self.caller)
        url = reverse("chat:end_call", args=[call.id])

        first = self.client.post(
            url,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        second = self.client.post(
            url,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        call.refresh_from_db()
        self.assertEqual(
            call.status,
            CallSession.STATUS_ENDED,
        )
        broadcast.assert_called_once_with(
            call,
            "call.ended",
        )

    @patch("chat.views.broadcast_call_event")
    def test_decline_does_not_overwrite_ended_call(
        self,
        broadcast,
    ):
        call = self.create_call(
            CallSession.STATUS_ENDED
        )
        self.client.force_login(self.receiver)

        response = self.client.post(
            reverse(
                "chat:decline_call",
                args=[call.id],
            ),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 200)
        call.refresh_from_db()
        self.assertEqual(
            call.status,
            CallSession.STATUS_ENDED,
        )
        broadcast.assert_not_called()

    @patch("chat.views.broadcast_call_event")
    def test_missed_call_is_created_once(
        self,
        broadcast,
    ):
        call = self.create_call()
        self.client.force_login(self.caller)
        url = reverse("chat:miss_call", args=[call.id])

        first = self.client.post(
            url,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        second = self.client.post(
            url,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        call.refresh_from_db()
        self.assertEqual(
            call.status,
            CallSession.STATUS_MISSED,
        )
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.receiver,
                notification_type=(
                    Notification.TYPE_MISSED_CALL
                ),
                related_object_type=(
                    "chat.callsession"
                ),
                related_object_id=call.id,
            ).count(),
            1,
        )
        broadcast.assert_called_once_with(
            call,
            "call.missed",
        )

    def test_payload_contains_recovery_urls(self):
        call = self.create_call()
        payload = build_call_payload(call)

        self.assertEqual(
            payload["status"],
            CallSession.STATUS_RINGING,
        )
        self.assertEqual(
            payload["status_url"],
            reverse(
                "chat:call_status",
                args=[call.id],
            ),
        )
        self.assertEqual(
            payload["miss_url"],
            reverse(
                "chat:miss_call",
                args=[call.id],
            ),
        )
        self.assertEqual(
            payload["accept_post_url"],
            reverse(
                "chat:accept_call",
                args=[call.id],
            ),
        )
