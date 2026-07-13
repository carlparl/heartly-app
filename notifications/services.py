from django.db import transaction

from .models import Notification


def notify(
    *,
    recipient,
    title,
    message="",
    notification_type=Notification.TYPE_SYSTEM,
    actor=None,
    url="",
    related_object_type="",
    related_object_id=None,
):
    """
    Create one notification. A post-save signal broadcasts it immediately
    after the database transaction commits.
    """
    if recipient is None:
        return None

    if actor is not None and actor.pk == recipient.pk:
        return None

    return Notification.objects.create(
        recipient=recipient,
        actor=actor,
        notification_type=notification_type,
        title=title,
        message=message,
        url=url,
        related_object_type=related_object_type,
        related_object_id=related_object_id,
    )


def notify_once(
    *,
    recipient,
    title,
    message="",
    notification_type=Notification.TYPE_SYSTEM,
    actor=None,
    url="",
    related_object_type="",
    related_object_id=None,
):
    """
    Avoid duplicate alerts for the same actor/action/object while an
    unresolved notification already exists.
    """
    lookup = {
        "recipient": recipient,
        "actor": actor,
        "notification_type": notification_type,
        "related_object_type": related_object_type,
        "related_object_id": related_object_id,
        "is_resolved": False,
    }

    with transaction.atomic():
        existing = (
            Notification.objects.select_for_update()
            .filter(**lookup)
            .order_by("-created_at")
            .first()
        )
        if existing:
            existing.title = title
            existing.message = message
            existing.url = url
            existing.is_read = False
            existing.save()
            return existing

        return Notification.objects.create(
            title=title,
            message=message,
            url=url,
            **lookup,
        )
