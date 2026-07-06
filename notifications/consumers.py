from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from chat.models import Call


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close()
            return

        self.group_name = f"heartly_user_{self.user.id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        event_type = content.get("type")

        if event_type == "call.decline":
            await self.decline_call(content)

    async def notification_event(self, event):
        await self.send_json(event["payload"])

    async def decline_call(self, content):
        call_id = content.get("call_id")
        thread_id = content.get("thread_id")

        if not call_id or not thread_id:
            return

        await self.mark_call_declined(call_id)

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
    def mark_call_declined(self, call_id):
        Call.objects.filter(
            id=call_id,
            receiver=self.user,
        ).update(
            status=Call.STATUS_DECLINED,
            ended_at=timezone.now(),
        )