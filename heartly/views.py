from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
def notifications_home(request):
    active_filter = request.GET.get("filter", "all")

    notifications_queryset = (
        Notification.objects
        .select_related("actor")
        .filter(
            recipient=request.user,
            is_resolved=False,
        )
        .order_by("-created_at")
    )

    valid_type_filters = [
        Notification.TYPE_LIKE,
        Notification.TYPE_COMMENT,
        Notification.TYPE_MESSAGE,
        Notification.TYPE_MATCH,
        Notification.TYPE_CALL,
        Notification.TYPE_SYSTEM,
    ]

    if active_filter == "unread":
        notifications_queryset = notifications_queryset.filter(is_read=False)

    elif active_filter in valid_type_filters:
        notifications_queryset = notifications_queryset.filter(
            notification_type=active_filter,
        )

    unread_count = Notification.objects.filter(
        recipient=request.user,
        is_read=False,
        is_resolved=False,
    ).count()

    notifications = notifications_queryset[:80]

    return render(
        request,
        "notifications/notifications_home.html",
        {
            "notifications": notifications,
            "unread_count": unread_count,
            "active_filter": active_filter,
        },
    )


@login_required
def open_notification(request, notification_id):
    notification = get_object_or_404(
        Notification,
        id=notification_id,
        recipient=request.user,
    )

    notification.is_read = True
    notification.save(update_fields=["is_read"])

    return redirect(notification.get_target_url())


@login_required
@require_POST
def mark_notifications_read(request):
    Notification.objects.filter(
        recipient=request.user,
        is_read=False,
        is_resolved=False,
    ).update(is_read=True)

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
    notification.resolved_at = timezone.now()
    notification.save(
        update_fields=[
            "is_read",
            "is_resolved",
            "resolved_at",
        ]
    )

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
        resolved_at=timezone.now(),
    )

    return redirect("notifications:notifications_home")