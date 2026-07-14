import json
import logging
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings

from .models import Notification, PushSubscription
from .utils import notification_icon


logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="heartly-push")


def push_is_configured():
    return bool(
        getattr(settings, "VAPID_PUBLIC_KEY", "")
        and getattr(settings, "VAPID_PRIVATE_KEY", "")
        and getattr(settings, "VAPID_SUBJECT", "")
    )


def send_notification_push(notification_id):
    if not push_is_configured():
        return 0

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.warning("pywebpush is not installed; browser push is disabled.")
        return 0

    try:
        notification = Notification.objects.get(
            pk=notification_id,
            is_resolved=False,
        )
    except Notification.DoesNotExist:
        return 0

    payload = json.dumps(
        {
            "title": notification.title or "Heartly update",
            "body": (
                notification.message
                or notification_icon(notification.notification_type)
            )[:240],
            "url": notification.url or "/notifications/",
            "tag": f"heartly-{notification.notification_type}-{notification.pk}",
            "icon": "/pwa/icon-192.png",
            "badge": "/pwa/icon-192.png",
        }
    )

    delivered = 0
    subscriptions = PushSubscription.objects.filter(
        user_id=notification.recipient_id,
        enabled=True,
    )
    for subscription in subscriptions.iterator():
        try:
            webpush(
                subscription_info=subscription.as_webpush_dict(),
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUBJECT},
                ttl=300,
                timeout=5,
            )
            delivered += 1
        except WebPushException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in {404, 410}:
                subscription.delete()
            else:
                logger.warning(
                    "Push delivery failed for subscription %s (HTTP %s).",
                    subscription.pk,
                    status_code or "unknown",
                )
        except Exception:
            logger.exception("Unexpected Heartly push delivery error.")

    return delivered


def enqueue_notification_push(notification_id):
    if push_is_configured():
        _executor.submit(send_notification_push, notification_id)
