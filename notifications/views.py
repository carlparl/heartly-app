from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .models import Notification
from .utils import notification_snapshot, visible_notifications_for


def wants_json(request):
    return (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
    )


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
@require_GET
def notification_snapshot_view(request):
    return JsonResponse(notification_snapshot(request.user))


@login_required
@require_GET
def unread_count(request):
    count = visible_notifications_for(request.user).filter(
        is_read=False
    ).count()
    return JsonResponse({"unread_count": count})


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
    notification.save(
        update_fields=["is_read", "is_resolved", "updated_at"]
    )

    if wants_json(request):
        return JsonResponse({"ok": True, "notification_id": notification.id})

    messages.success(request, "Notification cleared.")
    return redirect("notifications:notifications_home")


@login_required
@require_POST
def mark_notifications_read(request):
    updated = Notification.objects.filter(
        recipient=request.user,
        is_resolved=False,
        is_read=False,
    ).update(is_read=True)

    if wants_json(request):
        return JsonResponse({"ok": True, "updated": updated})

    messages.success(request, "Notifications marked as read.")
    return redirect("notifications:notifications_home")


@login_required
@require_POST
def clear_all_notifications(request):
    updated = Notification.objects.filter(
        recipient=request.user,
        is_resolved=False,
    ).update(
        is_read=True,
        is_resolved=True,
    )

    if wants_json(request):
        return JsonResponse({"ok": True, "updated": updated})

    messages.success(request, "All notifications cleared.")
    return redirect("notifications:notifications_home")
