import json

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import Conversation, Message


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        self.room_group_name = f"chat_{self.conversation_id}"

        if not self.user.is_authenticated:
            await self.close()
            return

        is_participant = await self.user_is_participant()

        if not is_participant:
            await self.close()
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )

        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        content = data.get("message", "").strip()

        if not content:
            return

        if len(content) > 2000:
            content = content[:2000]

        message_data = await self.save_message(content)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "message": message_data,
            },
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event["message"]))

    @sync_to_async
    def user_is_participant(self):
        return Conversation.objects.filter(
            id=self.conversation_id,
        ).filter(
            user_one=self.user,
        ).exists() or Conversation.objects.filter(
            id=self.conversation_id,
        ).filter(
            user_two=self.user,
        ).exists()

    @sync_to_async
    def save_message(self, content):
        conversation = Conversation.objects.get(id=self.conversation_id)

        message = Message.objects.create(
            conversation=conversation,
            sender=self.user,
            content=content,
        )

        conversation.save(update_fields=["updated_at"])

        sender_name = (
            self.user.get_full_name()
            or getattr(self.user, "email", "")
            or str(self.user)
        )

        return {
            "id": message.id,
            "conversation_id": conversation.id,
            "sender_id": self.user.id,
            "sender_name": sender_name,
            "content": message.content,
            "created_at": message.created_at.strftime("%H:%M"),
        }