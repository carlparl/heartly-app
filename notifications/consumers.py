from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from accounts.moderation import account_id_can_access
from chat.models import CallSession

from .models import Notification
from .utils import notification_snapshot


current_account_can_access = database_sync_to_async(
    account_id_can_access
)


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close(code=4401)
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
        await self.send_json(await self.get_snapshot())

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name,
            )

    async def receive_json(self, content, **kwargs):
        if not await current_account_can_access(self.user.id):
            await self.close(code=4403)
            return

        event_type = content.get("type")

        if event_type == "ping":
            await self.send_json({"type": "pong"})
        elif event_type == "notifications.refresh":
            await self.send_json(await self.get_snapshot())
        elif event_type == "notification.read":
            await self.mark_read(content.get("notification_id"))
        elif event_type == "notifications.read_all":
            await self.mark_all_read()
        elif event_type == "notification.clear":
            await self.clear_one(content.get("notification_id"))
        elif event_type == "notifications.clear_all":
            await self.clear_all()
        elif event_type == "call.decline":
            await self.decline_call(content)

    async def notification_event(self, event):
        await self.send_json(event["payload"])

    async def decline_call(self, content):
        call_id = content.get("call_id")
        thread_id = content.get("thread_id")

        if not call_id or not thread_id:
            return

        updated = await self.mark_call_declined(call_id)
        if not updated:
            return

        await self.channel_layer.group_send(
            f"chat_thread_{thread_id}",
            {
                "type": "chat.broadcast",
                "payload": {
                    "type": "call.declined",
                    "call_id": call_id,
                    "sender_id": self.user.id,
                },
            },
        )

    @database_sync_to_async
    def get_snapshot(self):
        return notification_snapshot(self.user)

    @database_sync_to_async
    def mark_read(self, notification_id):
        if not notification_id:
            return 0
        return Notification.objects.filter(
            id=notification_id,
            recipient=self.user,
            is_resolved=False,
        ).update(is_read=True)

    @database_sync_to_async
    def mark_all_read(self):
        return Notification.objects.filter(
            recipient=self.user,
            is_resolved=False,
            is_read=False,
        ).update(is_read=True)

    @database_sync_to_async
    def clear_one(self, notification_id):
        if not notification_id:
            return 0
        return Notification.objects.filter(
            id=notification_id,
            recipient=self.user,
        ).update(
            is_read=True,
            is_resolved=True,
        )

    @database_sync_to_async
    def clear_all(self):
        return Notification.objects.filter(
            recipient=self.user,
            is_resolved=False,
        ).update(
            is_read=True,
            is_resolved=True,
        )

    @database_sync_to_async
    def mark_call_declined(self, call_id):
        return CallSession.objects.filter(
            id=call_id,
            receiver=self.user,
        ).update(
            status=CallSession.STATUS_DECLINED,
            ended_at=timezone.now(),
        )
