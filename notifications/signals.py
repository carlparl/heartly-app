import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Notification
from .utils import notification_snapshot, serialize_notification


logger = logging.getLogger(__name__)


def user_group(user_id):
    return f"heartly_user_{user_id}"


def send_group_event(user_id, payload):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return False

    try:
        async_to_sync(channel_layer.group_send)(
            user_group(user_id),
            {
                "type": "notification.event",
                "payload": payload,
            },
        )
        return True
    except Exception:
        logger.exception(
            "Heartly could not publish a live notification for user %s.",
            user_id,
        )
        return False


def broadcast_snapshot(recipient_id):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        user = User.objects.get(pk=recipient_id)
    except User.DoesNotExist:
        return

    send_group_event(recipient_id, notification_snapshot(user))


@receiver(post_save, sender=Notification)
def notification_saved(sender, instance, created, **kwargs):
    recipient_id = instance.recipient_id

    def publish():
        # Queue browser push first. A temporary WebSocket/channel-layer error
        # must never prevent a closed app from receiving its system alert.
        if created:
            from .push import enqueue_notification_push

            enqueue_notification_push(instance.pk)

        payload = {
            "type": (
                "notification.created"
                if created
                else "notification.updated"
            ),
            "notification": serialize_notification(instance),
        }
        send_group_event(recipient_id, payload)
        broadcast_snapshot(recipient_id)

    transaction.on_commit(publish)


@receiver(post_delete, sender=Notification)
def notification_deleted(sender, instance, **kwargs):
    recipient_id = instance.recipient_id

    def publish():
        send_group_event(
            recipient_id,
            {
                "type": "notification.removed",
                "notification_id": instance.id,
            },
        )
        broadcast_snapshot(recipient_id)

    transaction.on_commit(publish)
