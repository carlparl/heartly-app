from __future__ import annotations

from django.db import transaction
from django.db.models import Q

from notifications.models import Notification

from .models import ChatMessage


def _mark_notifications_read(user, message_ids):
    ids = [int(item) for item in message_ids if item]
    if not ids:
        return 0

    return Notification.objects.filter(
        recipient=user,
        notification_type=Notification.TYPE_MESSAGE,
        related_object_type="chat.chatmessage",
        related_object_id__in=ids,
        is_read=False,
        is_resolved=False,
    ).update(is_read=True)


@transaction.atomic
def mark_thread_read_for_user(thread_id, user):
    unread_ids = list(
        ChatMessage.objects.select_for_update()
        .filter(thread_id=thread_id, is_read=False)
        .filter(Q(thread__user_one=user) | Q(thread__user_two=user))
        .exclude(sender=user)
        .values_list("id", flat=True)
    )
    if not unread_ids:
        return []

    ChatMessage.objects.filter(id__in=unread_ids).update(is_read=True)
    _mark_notifications_read(user, unread_ids)
    return unread_ids


@transaction.atomic
def mark_message_read_for_user(thread_id, message_id, user):
    if not message_id:
        return None

    message = (
        ChatMessage.objects.select_for_update()
        .filter(id=message_id, thread_id=thread_id)
        .filter(Q(thread__user_one=user) | Q(thread__user_two=user))
        .exclude(sender=user)
        .first()
    )
    if message is None:
        return None

    if message.is_read:
        _mark_notifications_read(user, [message.id])
        return None

    message.is_read = True
    message.save(update_fields=["is_read"])
    _mark_notifications_read(user, [message.id])
    return message.id
