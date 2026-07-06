from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from profiles.models import Profile

from .models import Notification


try:
    from profiles.blocking import hidden_user_ids_for
except Exception:
    hidden_user_ids_for = None


def model_has_field(model, field_name):
    return any(field.name == field_name for field in model._meta.fields)


def visible_notifications_for(user):
    hidden_ids = hidden_user_ids_for(user) if hidden_user_ids_for else set()

    notifications = Notification.objects.filter(
        recipient=user,
        is_resolved=False,
    ).select_related("actor", "recipient")

    if hidden_ids:
        notifications = notifications.exclude(actor_id__in=hidden_ids)

    if model_has_field(Profile, "hidden_by_moderation"):
        notifications = notifications.exclude(actor__profile__hidden_by_moderation=True)

    if model_has_field(Profile, "profile_visible"):
        notifications = notifications.exclude(actor__profile__profile_visible=False)

    return notifications.order_by("-created_at")


@login_required
def notifications_home(request):
    notifications = visible_notifications_for(request.user)

    unread_count = notifications.filter(is_read=False).count()

    return render(
        request,
        "notifications/notifications_home.html",
        {
            "notifications": notifications,
            "unread_count": unread_count,
        },
    )


@login_required
def open_notification(request, notification_id):
    notification = get_object_or_404(
        Notification,
        id=notification_id,
        recipient=request.user,
        is_resolved=False,
    )

    notification.is_read = True
    notification.save(update_fields=["is_read", "updated_at"])

    if notification.url:
        return redirect(notification.url)

    return redirect("notifications:notifications_home")


@login_required
@require_POST
def clear_notification(request, notification_id):
    notification = get_object_or_404(
        Notification,
        id=notification_id,
        recipient=request.user,
    )

    notification.is_read = True
    notification.is_resolved = True
    notification.save(update_fields=["is_read", "is_resolved", "updated_at"])

    messages.success(request, "Notification cleared.")
    return redirect("notifications:notifications_home")


@login_required
@require_POST
def mark_notifications_read(request):
    Notification.objects.filter(
        recipient=request.user,
        is_resolved=False,
        is_read=False,
    ).update(is_read=True)

    messages.success(request, "Notifications marked as read.")
    return redirect("notifications:notifications_home")


@login_required
@require_POST
def clear_all_notifications(request):
    Notification.objects.filter(
        recipient=request.user,
        is_resolved=False,
    ).update(
        is_read=True,
        is_resolved=True,
    )

    messages.success(request, "All notifications cleared.")
    return redirect("notifications:notifications_home")