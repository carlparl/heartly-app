from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from accounts.moderation import account_id_can_access
from profiles.models import Profile, UserBlock

from .models import CallSession, ChatMessage, ChatThread
from .realtime import (
    mark_message_read_for_user,
    mark_thread_read_for_user,
)

try:
    from profiles.blocking import block_exists_between
except Exception:
    block_exists_between = None

try:
    from notifications.models import Notification
except Exception:
    Notification = None


current_account_can_access = database_sync_to_async(
    account_id_can_access
)


def model_has_field(model, field_name):
    return any(field.name == field_name for field in model._meta.fields)


def display_name_for(user):
    profile, created = Profile.objects.get_or_create(user=user)
    return (
        getattr(profile, "display_name", "")
        or getattr(profile, "name", "")
        or user.get_full_name()
        or user.username
        or "Heartly User"
    )


class ThreadConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        self.thread_id = self.scope["url_route"]["kwargs"]["thread_id"]
        self.group_name = f"chat_thread_{self.thread_id}"

        if not self.user.is_authenticated:
            await self.close()
            return

        if not await current_account_can_access(self.user.id):
            await self.close(code=4403)
            return

        allowed = await self.user_can_access_thread()
        if not allowed:
            await self.close()
            return

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name,
        )
        await self.accept()

        read_ids = await self.mark_messages_read()
        if read_ids:
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "chat.broadcast",
                    "payload": {
                        "type": "chat.read",
                        "message_ids": read_ids,
                        "reader_id": self.user.id,
                    },
                },
            )

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if not await current_account_can_access(self.user.id):
            await self.close(code=4403)
            return

        if not await self.user_can_access_thread():
            await self.close()
            return

        event_type = content.get("type")

        if event_type == "chat.message":
            # HTTP is the only authoritative message-write path.
            await self.send_json(
                {
                    "type": "chat.error",
                    "message": "Send messages through the composer.",
                }
            )
        elif event_type == "typing.start":
            await self.relay_typing(True)
        elif event_type == "typing.stop":
            await self.relay_typing(False)
        elif event_type == "call.start":
            await self.send_json(
                {
                    "type": "chat.error",
                    "message": "Start calls through the call button.",
                }
            )
        elif event_type == "call.sync":
            await self.handle_call_sync(content)
        elif event_type == "call.accept":
            await self.handle_call_accept(content)
        elif event_type == "call.decline":
            await self.handle_call_decline(content)
        elif event_type == "call.end":
            await self.handle_call_end(content)
        elif event_type == "call.missed":
            await self.handle_call_missed(content)
        elif event_type in [
            "call.ready",
            "webrtc.offer",
            "webrtc.answer",
            "webrtc.ice",
        ]:
            await self.relay_call_signal(content)

    async def handle_chat_message(self, content):
        text = (content.get("text") or "").strip()
        reply_to_id = content.get("reply_to_id")

        if not text:
            return

        if len(text) > 1200:
            text = text[:1200]

        message_payload = await self.save_message(text, reply_to_id)

        if not message_payload:
            return

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat.broadcast",
                "payload": {
                    "type": "chat.message",
                    **message_payload,
                },
            },
        )

    async def relay_typing(self, is_typing):
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat.broadcast",
                "payload": {
                    "type": "typing",
                    "sender_id": self.user.id,
                    "is_typing": is_typing,
                },
            },
        )

    async def handle_call_start(self, content):
        call_type = content.get("call_type", "audio")

        if call_type not in ["audio", "video"]:
            call_type = "audio"

        call_payload = await self.create_call(call_type)

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat.broadcast",
                "payload": {
                    "type": "call.incoming",
                    **call_payload,
                },
            },
        )

        await self.channel_layer.group_send(
            f"heartly_user_{call_payload['receiver_id']}",
            {
                "type": "notification.event",
                "payload": {
                    "type": "incoming_call",
                    **call_payload,
                },
            },
        )

    async def handle_call_sync(self, content):
        call_id = content.get("call_id")
        state = await self.get_call_state(call_id)

        if state is None:
            await self.send_json(
                {
                    "type": "call.error",
                    "call_id": call_id,
                    "message": "Call is not available.",
                }
            )
            return

        await self.send_json(
            {
                "type": "call.state",
                **state,
            }
        )

    async def handle_call_accept(self, content):
        call_id = content.get("call_id")
        status = await self.answer_call(call_id)

        if status != CallSession.STATUS_ACCEPTED:
            return

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat.broadcast",
                "payload": {
                    "type": "call.accepted",
                    "call_id": call_id,
                    "sender_id": self.user.id,
                },
            },
        )

    async def handle_call_decline(self, content):
        call_id = content.get("call_id")
        updated = await self.close_call(
            call_id,
            CallSession.STATUS_DECLINED,
        )

        if not updated:
            return

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat.broadcast",
                "payload": {
                    "type": "call.declined",
                    "call_id": call_id,
                    "sender_id": self.user.id,
                },
            },
        )

    async def handle_call_end(self, content):
        call_id = content.get("call_id")
        updated = await self.close_call(
            call_id,
            CallSession.STATUS_ENDED,
        )

        if not updated:
            return

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat.broadcast",
                "payload": {
                    "type": "call.ended",
                    "call_id": call_id,
                    "sender_id": self.user.id,
                },
            },
        )

    async def handle_call_missed(self, content):
        call_id = content.get("call_id")
        missed_payload = await self.mark_call_missed(call_id)

        if not missed_payload:
            return

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat.broadcast",
                "payload": {
                    "type": "call.missed",
                    **missed_payload,
                },
            },
        )

        await self.channel_layer.group_send(
            f"heartly_user_{missed_payload['receiver_id']}",
            {
                "type": "notification.event",
                "payload": {
                    "type": "missed_call",
                    **missed_payload,
                },
            },
        )

    async def relay_call_signal(self, content):
        call_id = content.get("call_id")

        if not await self.user_can_access_call(call_id):
            return

        safe_content = dict(content)
        safe_content["sender_id"] = self.user.id

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat.broadcast",
                "payload": safe_content,
            },
        )

    async def chat_broadcast(self, event):
        payload = event["payload"]

        if (
            payload.get("type") == "chat.message"
            and int(payload.get("sender_id") or 0)
            != self.user.id
        ):
            message_id = (
                payload.get("message_id")
                or payload.get("id")
            )
            changed_id = await self.mark_message_read(
                message_id
            )

            if changed_id:
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        "type": "chat.broadcast",
                        "payload": {
                            "type": "chat.read",
                            "message_ids": [changed_id],
                            "reader_id": self.user.id,
                        },
                    },
                )

        await self.send_json(payload)

    @database_sync_to_async
    def user_can_access_thread(self):
        try:
            thread = ChatThread.objects.select_related("user_one", "user_two").get(id=self.thread_id)
        except ChatThread.DoesNotExist:
            return False

        if not thread.has_user(self.user):
            return False

        other_user = thread.other_user(self.user)

        if block_exists_between:
            if block_exists_between(self.user, other_user):
                return False
        else:
            if UserBlock.objects.filter(blocker=self.user, blocked=other_user).exists():
                return False
            if UserBlock.objects.filter(blocker=other_user, blocked=self.user).exists():
                return False

        profile, created = Profile.objects.get_or_create(user=other_user)

        if getattr(profile, "profile_visible", True) is False:
            return False

        if getattr(profile, "hidden_by_moderation", False):
            return False

        return True

    @database_sync_to_async
    def user_can_access_call(self, call_id):
        if not call_id:
            return False

        return CallSession.objects.filter(
            Q(caller=self.user) | Q(receiver=self.user),
            id=call_id,
            thread_id=self.thread_id,
            status=CallSession.STATUS_ACCEPTED,
        ).exists()

    @database_sync_to_async
    def get_call_state(self, call_id):
        if not call_id:
            return None

        call = (
            CallSession.objects
            .select_related(
                "caller",
                "receiver",
                "thread",
            )
            .filter(
                Q(caller=self.user) | Q(receiver=self.user),
                id=call_id,
                thread_id=self.thread_id,
            )
            .first()
        )

        if call is None:
            return None

        call_url = reverse(
            "chat:call_room",
            args=[call.id],
        )

        return {
            "call_id": call.id,
            "thread_id": call.thread_id,
            "call_type": call.call_type,
            "status": call.status,
            "started_at": call.started_at.isoformat(),
            "caller_id": call.caller_id,
            "receiver_id": call.receiver_id,
            "caller_name": display_name_for(call.caller),
            "receiver_name": display_name_for(call.receiver),
            "url": call_url,
            "accept_url": call_url,
            "accept_post_url": reverse(
                "chat:accept_call",
                args=[call.id],
            ),
            "decline_url": reverse(
                "chat:decline_call",
                args=[call.id],
            ),
            "end_url": reverse(
                "chat:end_call",
                args=[call.id],
            ),
            "miss_url": reverse(
                "chat:miss_call",
                args=[call.id],
            ),
            "status_url": reverse(
                "chat:call_status",
                args=[call.id],
            ),
        }

    @database_sync_to_async
    def mark_messages_read(self):
        return mark_thread_read_for_user(
            self.thread_id,
            self.user,
        )

    @database_sync_to_async
    def mark_message_read(self, message_id):
        return mark_message_read_for_user(
            self.thread_id,
            message_id,
            self.user,
        )

    @database_sync_to_async
    def save_message(self, text, reply_to_id=None):
        thread = ChatThread.objects.get(id=self.thread_id)
        reply_to = None

        if reply_to_id:
            reply_to = ChatMessage.objects.filter(id=reply_to_id, thread=thread).first()

        message = ChatMessage.objects.create(
            thread=thread,
            sender=self.user,
            reply_to=reply_to,
            text=text,
        )

        thread.save()
        self.create_message_notification(message)

        payload = {
            "id": message.id,
            "message_id": message.id,
            "thread_id": thread.id,
            "sender_id": self.user.id,
            "sender_name": display_name_for(self.user),
            "text": message.text,
            "created_at": timezone.localtime(message.created_at).strftime("%H:%M"),
            "attachments": [],
            "reply_to": None,
        }

        if reply_to:
            first_attachment = reply_to.attachments.first()
            if reply_to.text:
                preview = reply_to.text[:110]
            elif first_attachment:
                preview = first_attachment.attachment_type.title()
            else:
                preview = "Message"

            payload["reply_to"] = {
                "id": reply_to.id,
                "sender_id": reply_to.sender_id,
                "sender_name": display_name_for(reply_to.sender),
                "text": preview,
            }

        return payload


    @database_sync_to_async
    def create_call(self, call_type):
        thread = ChatThread.objects.select_related("user_one", "user_two").get(id=self.thread_id)
        receiver = thread.other_user(self.user)

        call = CallSession.objects.create(
            thread=thread,
            caller=self.user,
            receiver=receiver,
            call_type=call_type,
            status=CallSession.STATUS_RINGING,
        )

        caller_name = display_name_for(self.user)
        call_url = reverse("chat:call_room", args=[call.id])

        self.create_call_notification(
            recipient=receiver,
            actor=self.user,
            call=call,
            title="Incoming call",
            message=f"{caller_name} is calling you.",
            notification_type=getattr(Notification, "TYPE_CALL", "call") if Notification else "call",
            url=call_url,
        )

        return {
            "call_id": call.id,
            "call_type": call.call_type,
            "thread_id": thread.id,
            "caller_id": self.user.id,
            "receiver_id": receiver.id,
            "caller_name": caller_name,
            "url": call_url,
            "accept_url": call_url,
            "decline_url": reverse("chat:decline_call", args=[call.id]),
        }

    @database_sync_to_async
    def answer_call(self, call_id):
        if not call_id:
            return None

        call = CallSession.objects.filter(
            id=call_id,
            thread_id=self.thread_id,
            receiver=self.user,
        ).first()

        if call is None:
            return None

        if call.status == CallSession.STATUS_RINGING:
            call.status = CallSession.STATUS_ACCEPTED
            call.accepted_at = timezone.now()
            call.save(
                update_fields=[
                    "status",
                    "accepted_at",
                ]
            )

        return call.status

    @database_sync_to_async
    def close_call(self, call_id, status):
        if not call_id:
            return False

        updated = CallSession.objects.filter(
            Q(caller=self.user) | Q(receiver=self.user),
            id=call_id,
            thread_id=self.thread_id,
            status__in=[
                CallSession.STATUS_RINGING,
                CallSession.STATUS_ACCEPTED,
            ],
        ).update(
            status=status,
            ended_at=timezone.now(),
        )
        return bool(updated)

    @database_sync_to_async
    def mark_call_missed(self, call_id):
        if not call_id:
            return None

        call = (
            CallSession.objects
            .select_related("thread", "caller", "receiver")
            .filter(
                id=call_id,
                thread_id=self.thread_id,
                caller=self.user,
                status=CallSession.STATUS_RINGING,
            )
            .first()
        )

        if not call:
            return None

        call.status = CallSession.STATUS_MISSED
        call.ended_at = timezone.now()
        call.save(update_fields=["status", "ended_at"])

        caller_name = display_name_for(call.caller)
        call_url = reverse("chat:call_room", args=[call.id])

        self.create_call_notification(
            recipient=call.receiver,
            actor=call.caller,
            call=call,
            title="Missed call",
            message=f"You missed a {call.call_type} call from {caller_name}.",
            notification_type=getattr(Notification, "TYPE_MISSED_CALL", "missed_call") if Notification else "missed_call",
            url=call_url,
        )

        return {
            "call_id": call.id,
            "call_type": call.call_type,
            "thread_id": call.thread.id,
            "caller_id": call.caller.id,
            "receiver_id": call.receiver.id,
            "caller_name": caller_name,
            "url": call_url,
            "accept_url": call_url,
        }

    def create_message_notification(self, message):
        if Notification is None:
            return

        thread = message.thread
        recipient = thread.other_user(message.sender)

        try:
            notification_data = {
                "recipient": recipient,
                "actor": message.sender,
            }

            if model_has_field(Notification, "notification_type"):
                notification_data["notification_type"] = getattr(Notification, "TYPE_MESSAGE", "message")

            if model_has_field(Notification, "title"):
                notification_data["title"] = "New message"

            if model_has_field(Notification, "message"):
                notification_data["message"] = "You received a new message."

            if model_has_field(Notification, "url"):
                notification_data["url"] = reverse("chat:chat_room", args=[thread.id])

            if model_has_field(Notification, "related_object_type"):
                notification_data["related_object_type"] = "chat.chatmessage"

            if model_has_field(Notification, "related_object_id"):
                notification_data["related_object_id"] = message.id

            Notification.objects.create(**notification_data)
        except Exception:
            return

    def create_call_notification(self, recipient, actor, call, title, message, notification_type, url):
        if Notification is None:
            return

        try:
            notification_data = {
                "recipient": recipient,
                "actor": actor,
            }

            if model_has_field(Notification, "notification_type"):
                notification_data["notification_type"] = notification_type

            if model_has_field(Notification, "title"):
                notification_data["title"] = title

            if model_has_field(Notification, "message"):
                notification_data["message"] = message

            if model_has_field(Notification, "url"):
                notification_data["url"] = url

            if model_has_field(Notification, "related_object_type"):
                notification_data["related_object_type"] = "chat.call"

            if model_has_field(Notification, "related_object_id"):
                notification_data["related_object_id"] = call.id

            Notification.objects.create(**notification_data)
        except Exception:
            return


class GlobalCallConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close()
            return

        if not await current_account_can_access(self.user.id):
            await self.close(code=4403)
            return

        self.group_name = f"heartly_user_{self.user.id}"
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name,
        )
        await self.accept()

        active_call = await self.active_incoming_call()
        if active_call:
            await self.send_json(active_call)
        else:
            await self.send_json(
                {"type": "call.none"}
            )

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    @database_sync_to_async
    def active_incoming_call(self):
        call = (
            CallSession.objects
            .select_related(
                "caller",
                "receiver",
                "thread",
            )
            .filter(
                receiver=self.user,
                status=CallSession.STATUS_RINGING,
            )
            .order_by("-started_at")
            .first()
        )

        if call is None:
            return None

        call_url = reverse(
            "chat:call_room",
            args=[call.id],
        )

        return {
            "type": "incoming_call",
            "call_id": call.id,
            "thread_id": call.thread_id,
            "call_type": call.call_type,
            "status": call.status,
            "started_at": call.started_at.isoformat(),
            "caller_id": call.caller_id,
            "receiver_id": call.receiver_id,
            "caller_name": display_name_for(call.caller),
            "receiver_name": display_name_for(call.receiver),
            "url": call_url,
            "accept_url": call_url,
            "accept_post_url": reverse(
                "chat:accept_call",
                args=[call.id],
            ),
            "decline_url": reverse(
                "chat:decline_call",
                args=[call.id],
            ),
            "end_url": reverse(
                "chat:end_call",
                args=[call.id],
            ),
        }

    async def notification_event(self, event):
        await self.send_json(event.get("payload", {}))

    async def chat_broadcast(self, event):
        await self.send_json(event.get("payload", {}))
