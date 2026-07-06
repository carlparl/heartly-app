from profiles.blocking import hidden_user_ids_for
from profiles.models import Profile

from .models import Notification


def model_has_field(model, field_name):
    return any(field.name == field_name for field in model._meta.fields)


def unread_notifications(request):
    if not request.user.is_authenticated:
        return {
            "unread_notifications_count": 0,
        }

    hidden_ids = hidden_user_ids_for(request.user)

    notifications = Notification.objects.filter(
        recipient=request.user,
        is_read=False,
        is_resolved=False,
    ).exclude(actor_id__in=hidden_ids)

    if model_has_field(Profile, "hidden_by_moderation"):
        notifications = notifications.exclude(actor__profile__hidden_by_moderation=True)

    if model_has_field(Profile, "profile_visible"):
        notifications = notifications.exclude(actor__profile__profile_visible=False)

    return {
        "unread_notifications_count": notifications.count(),
    }