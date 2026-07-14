from django.urls import reverse
from django.utils import timezone
from django.db.models import Q

from profiles.models import Profile

from .models import Notification


def model_has_field(model, field_name):
    return any(field.name == field_name for field in model._meta.fields)


def hidden_user_ids(user):
    try:
        from profiles.blocking import hidden_user_ids_for
        return hidden_user_ids_for(user)
    except Exception:
        return set()


def visible_notifications_for(user):
    notifications = Notification.objects.filter(
        recipient=user,
        is_resolved=False,
    ).select_related("actor", "recipient")

    blocked_ids = hidden_user_ids(user)
    if blocked_ids:
        notifications = notifications.exclude(
            Q(actor_id__in=blocked_ids)
            & ~Q(notification_type=Notification.TYPE_BROADCAST)
        )

    if model_has_field(Profile, "hidden_by_moderation"):
        notifications = notifications.exclude(
            Q(actor__profile__hidden_by_moderation=True)
            & ~Q(notification_type=Notification.TYPE_BROADCAST)
        )

    if model_has_field(Profile, "profile_visible"):
        notifications = notifications.exclude(
            Q(actor__profile__profile_visible=False)
            & ~Q(notification_type=Notification.TYPE_BROADCAST)
        )

    return notifications.order_by("-created_at")


def notification_icon(notification_type):
    return {
        Notification.TYPE_LIKE: "❤️",
        Notification.TYPE_COMMENT: "💬",
        Notification.TYPE_MESSAGE: "📩",
        Notification.TYPE_MATCH: "💞",
        Notification.TYPE_CALL: "📞",
        Notification.TYPE_MISSED_CALL: "📵",
        Notification.TYPE_REPORT: "🛡️",
        Notification.TYPE_SYSTEM: "🔔",
        Notification.TYPE_BROADCAST: "📣",
        Notification.TYPE_BROADCAST_FEEDBACK: "📝",
    }.get(notification_type, "🔔")


def actor_name(notification):
    actor = notification.actor
    if actor is None:
        return ""

    try:
        display_name = actor.profile.display_name
    except Exception:
        display_name = ""

    return display_name or actor.username


def serialize_notification(notification):
    return {
        "id": notification.id,
        "type": notification.notification_type,
        "title": notification.title,
        "message": notification.message,
        "url": notification.url or reverse(
            "notifications:open_notification",
            args=[notification.id],
        ),
        "open_url": reverse(
            "notifications:open_notification",
            args=[notification.id],
        ),
        "clear_url": reverse(
            "notifications:clear_notification",
            args=[notification.id],
        ),
        "icon": notification_icon(notification.notification_type),
        "actor_name": actor_name(notification),
        "actor_id": notification.actor_id,
        "is_read": notification.is_read,
        "is_resolved": notification.is_resolved,
        "created_at": notification.created_at.isoformat(),
        "created_label": timezone.localtime(notification.created_at).strftime(
            "%b %d, %H:%M"
        ),
    }


def notification_snapshot(user, limit=25):
    queryset = visible_notifications_for(user)
    return {
        "type": "notifications.snapshot",
        "unread_count": queryset.filter(is_read=False).count(),
        "notifications": [
            serialize_notification(item)
            for item in queryset[:limit]
        ],
    }
