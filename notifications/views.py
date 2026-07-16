import json
import re
import secrets
from urllib.parse import urlparse

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import Notification, PushSubscription
from .utils import notification_snapshot, visible_notifications_for


BROADCAST_FEEDBACK_ALLOWED = "broadcast_feedback_allowed"
BROADCAST_READ_ONLY = "broadcast_read_only"
MAX_BROADCAST_MESSAGE_LENGTH = 5000
MAX_FEEDBACK_LENGTH = 1000


def wants_json(request):
    return (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
    )


def require_staff(user):
    if not user.is_active or not user.is_staff:
        raise PermissionDenied("Only Heartly staff can send broadcasts.")


def create_broadcast_batch_id():
    """Return a positive ID that is not already used by another broadcast."""
    for _ in range(20):
        candidate = secrets.randbelow(2_147_483_646) + 1
        exists = Notification.objects.filter(
            notification_type=Notification.TYPE_BROADCAST,
            related_object_id=candidate,
        ).exists()
        if not exists:
            return candidate

    raise RuntimeError("Could not allocate a broadcast ID. Please try again.")


def refresh_notification_users(user_ids, notification_ids=None):
    """Push fresh notification snapshots after bulk delivery commits."""
    from .signals import broadcast_snapshot
    from .push import enqueue_notification_push

    for user_id in user_ids:
        broadcast_snapshot(user_id)

    for notification_id in notification_ids or []:
        enqueue_notification_push(notification_id)


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
@require_http_methods(["GET", "POST"])
def create_broadcast(request):
    require_staff(request.user)

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        message_text = request.POST.get("message", "").strip()
        allow_feedback = request.POST.get("allow_feedback") == "on"

        errors = []
        if not title:
            errors.append("Add a broadcast title.")
        elif len(title) > 120:
            errors.append("The title must be 120 characters or fewer.")

        if not message_text:
            errors.append("Add the broadcast message.")
        elif len(message_text) > MAX_BROADCAST_MESSAGE_LENGTH:
            errors.append(
                f"The message must be {MAX_BROADCAST_MESSAGE_LENGTH} characters or fewer."
            )

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(
                request,
                "notifications/broadcast_form.html",
                {
                    "draft_title": title,
                    "draft_message": message_text,
                    "draft_allow_feedback": allow_feedback,
                },
            )

        User = get_user_model()
        recipients = list(
            User.objects.filter(is_active=True).only("id")
        )
        if not recipients:
            messages.error(request, "There are no active Heartly users to notify.")
            return redirect("notifications:create_broadcast")

        batch_id = create_broadcast_batch_id()
        detail_url = reverse(
            "notifications:broadcast_detail",
            args=[batch_id],
        )
        feedback_mode = (
            BROADCAST_FEEDBACK_ALLOWED
            if allow_feedback
            else BROADCAST_READ_ONLY
        )

        notifications = [
            Notification(
                recipient_id=recipient.id,
                actor=request.user,
                notification_type=Notification.TYPE_BROADCAST,
                title=title,
                message=message_text,
                url=detail_url,
                related_object_type=feedback_mode,
                related_object_id=batch_id,
            )
            for recipient in recipients
        ]
        recipient_ids = [recipient.id for recipient in recipients]

        with transaction.atomic():
            Notification.objects.bulk_create(notifications, batch_size=500)
            notification_ids = [item.id for item in notifications if item.id]
            transaction.on_commit(
                lambda user_ids=recipient_ids, push_ids=notification_ids: (
                    refresh_notification_users(user_ids, push_ids)
                )
            )

        messages.success(
            request,
            f"Broadcast sent to {len(recipients)} active user"
            f"{'s' if len(recipients) != 1 else ''}.",
        )
        return redirect("notifications:broadcast_detail", batch_id=batch_id)

    return render(request, "notifications/broadcast_form.html")


@login_required
@require_http_methods(["GET", "POST"])
def broadcast_detail(request, batch_id):
    broadcast = get_object_or_404(
        Notification.objects.select_related("actor"),
        recipient=request.user,
        notification_type=Notification.TYPE_BROADCAST,
        related_object_id=batch_id,
    )

    if not broadcast.is_read:
        broadcast.is_read = True
        broadcast.save(update_fields=["is_read", "updated_at"])

    feedback_allowed = (
        broadcast.related_object_type == BROADCAST_FEEDBACK_ALLOWED
        and broadcast.actor_id != request.user.id
        and broadcast.actor_id is not None
    )
    existing_feedback = None
    if broadcast.actor_id:
        existing_feedback = Notification.objects.filter(
            recipient_id=broadcast.actor_id,
            actor=request.user,
            notification_type=Notification.TYPE_BROADCAST_FEEDBACK,
            related_object_id=batch_id,
        ).first()

    if request.method == "POST":
        if not feedback_allowed:
            raise PermissionDenied("Feedback is not enabled for this broadcast.")

        feedback_text = request.POST.get("feedback", "").strip()
        if not feedback_text:
            messages.error(request, "Write your feedback before sending.")
        elif len(feedback_text) > MAX_FEEDBACK_LENGTH:
            messages.error(
                request,
                f"Feedback must be {MAX_FEEDBACK_LENGTH} characters or fewer.",
            )
        else:
            with transaction.atomic():
                locked_broadcast = get_object_or_404(
                    Notification.objects.select_for_update(),
                    pk=broadcast.pk,
                    recipient=request.user,
                )
                existing_feedback = Notification.objects.filter(
                    recipient_id=locked_broadcast.actor_id,
                    actor=request.user,
                    notification_type=Notification.TYPE_BROADCAST_FEEDBACK,
                    related_object_id=batch_id,
                ).first()

                if existing_feedback:
                    messages.info(
                        request,
                        "You already sent feedback for this broadcast.",
                    )
                else:
                    Notification.objects.create(
                        recipient_id=locked_broadcast.actor_id,
                        actor=request.user,
                        notification_type=Notification.TYPE_BROADCAST_FEEDBACK,
                        title=f"Feedback: {locked_broadcast.title}"[:120],
                        message=feedback_text,
                        url=reverse("notifications:notifications_home"),
                        related_object_type="broadcast_feedback",
                        related_object_id=batch_id,
                    )
                    messages.success(request, "Your feedback was sent.")

            return redirect(
                "notifications:broadcast_detail",
                batch_id=batch_id,
            )

    return render(
        request,
        "notifications/broadcast_detail.html",
        {
            "broadcast": broadcast,
            "feedback_allowed": feedback_allowed,
            "existing_feedback": existing_feedback,
            "max_feedback_length": MAX_FEEDBACK_LENGTH,
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


@login_required
@require_GET
def push_config(request):
    public_key = getattr(
        settings,
        "VAPID_PUBLIC_KEY",
        "",
    )
    enabled = bool(
        public_key
        and getattr(settings, "VAPID_PRIVATE_KEY", "")
        and getattr(settings, "VAPID_SUBJECT", "")
    )
    subscription_count = (
        PushSubscription.objects.filter(
            user=request.user,
            enabled=True,
        ).count()
    )

    return JsonResponse(
        {
            "enabled": enabled,
            "public_key": public_key,
            "has_subscription": subscription_count > 0,
            "subscription_count": subscription_count,
        }
    )


def _request_json(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


@login_required
@require_POST
def push_subscribe(request):
    payload = _request_json(request)
    if not isinstance(payload, dict):
        return JsonResponse({"ok": False, "error": "Invalid JSON."}, status=400)

    endpoint = str(payload.get("endpoint") or "").strip()
    keys = payload.get("keys") or {}
    if not isinstance(keys, dict):
        return JsonResponse(
            {"ok": False, "error": "Invalid push subscription keys."},
            status=400,
        )
    p256dh = str(keys.get("p256dh") or "").strip()
    auth = str(keys.get("auth") or "").strip()
    parsed_endpoint = urlparse(endpoint)

    if (
        parsed_endpoint.scheme != "https"
        or not parsed_endpoint.netloc
        or len(endpoint) > 4096
        or not p256dh
        or len(p256dh) > 512
        or not auth
        or len(auth) > 512
    ):
        return JsonResponse(
            {"ok": False, "error": "Invalid push subscription."},
            status=400,
        )

    installation_id = str(
        payload.get("installation_id") or ""
    ).strip()
    if not re.fullmatch(
        r"[A-Za-z0-9_-]{16,80}",
        installation_id,
    ):
        installation_id = ""

    raw_user_agent = request.headers.get(
        "user-agent",
        "",
    )[:420]
    installation_marker = (
        f"heartly-installation:{installation_id}"
        if installation_id
        else ""
    )
    stored_user_agent = raw_user_agent
    if installation_marker:
        stored_user_agent = (
            f"{raw_user_agent} | {installation_marker}"
        )[:500]

    with transaction.atomic():
        duplicate_query = Q(user_agent=raw_user_agent)
        if raw_user_agent:
            duplicate_query |= Q(
                user_agent__startswith=(
                    raw_user_agent
                    + " | heartly-installation:"
                )
            )
        if installation_marker:
            duplicate_query |= Q(
                user_agent__endswith=installation_marker
            )

        removed_duplicates, _ = (
            PushSubscription.objects
            .filter(
                user=request.user,
            )
            .exclude(endpoint=endpoint)
            .filter(duplicate_query)
            .delete()
        )

        subscription, created = (
            PushSubscription.objects.update_or_create(
                endpoint=endpoint,
                defaults={
                    "user": request.user,
                    "p256dh": p256dh,
                    "auth": auth,
                    "user_agent": stored_user_agent,
                    "enabled": True,
                },
            )
        )

    return JsonResponse(
        {
            "ok": True,
            "created": created,
            "subscription_id": subscription.id,
            "removed_duplicates": removed_duplicates,
        }
    )


@login_required
@require_POST
def push_unsubscribe(request):
    payload = _request_json(request)
    endpoint = str((payload or {}).get("endpoint") or "").strip()
    if not endpoint:
        return JsonResponse({"ok": False, "error": "Missing endpoint."}, status=400)

    deleted, _ = PushSubscription.objects.filter(
        user=request.user,
        endpoint=endpoint,
    ).delete()
    return JsonResponse({"ok": True, "deleted": bool(deleted)})
