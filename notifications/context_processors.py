from profiles.models import Profile

from .utils import hidden_user_ids, model_has_field


def unread_notifications(request):
    if not request.user.is_authenticated:
        return {"unread_notifications_count": 0}

    notifications = request.user.notifications.filter(
        is_read=False,
        is_resolved=False,
    )

    blocked_ids = hidden_user_ids(request.user)
    if blocked_ids:
        notifications = notifications.exclude(actor_id__in=blocked_ids)

    if model_has_field(Profile, "hidden_by_moderation"):
        notifications = notifications.exclude(
            actor__profile__hidden_by_moderation=True
        )

    if model_has_field(Profile, "profile_visible"):
        notifications = notifications.exclude(
            actor__profile__profile_visible=False
        )

    return {
        "unread_notifications_count": notifications.count(),
    }
