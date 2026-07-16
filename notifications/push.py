from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.db import close_old_connections

from .models import Notification, PushSubscription
from .utils import notification_icon


logger = logging.getLogger(__name__)

try:
    from pywebpush import WebPushException, webpush
except ImportError:  # pragma: no cover - production requirements include it.
    WebPushException = Exception
    webpush = None


def _setting_int(name, default, minimum=1, maximum=None):
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = int(default)

    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _setting_float(name, default, minimum=0.0, maximum=None):
    try:
        value = float(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = float(default)

    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


_executor = ThreadPoolExecutor(
    max_workers=_setting_int(
        "HEARTLY_PUSH_WORKERS",
        4,
        minimum=1,
        maximum=8,
    ),
    thread_name_prefix="heartly-push",
)


def push_is_configured():
    return bool(
        getattr(settings, "VAPID_PUBLIC_KEY", "")
        and getattr(settings, "VAPID_PRIVATE_KEY", "")
        and getattr(settings, "VAPID_SUBJECT", "")
        and webpush is not None
    )


def notification_open_url(notification):
    return f"/notifications/{notification.pk}/open/"


def notification_dedupe_key(notification):
    if (
        notification.notification_type
        in {
            Notification.TYPE_CALL,
            Notification.TYPE_MISSED_CALL,
        }
        and notification.related_object_id
    ):
        return (
            f"heartly-call-"
            f"{notification.related_object_id}"
        )

    return (
        f"heartly-{notification.notification_type}-"
        f"{notification.pk}"
    )


def notification_push_payload(notification):
    created_at = getattr(notification, "created_at", None)
    timestamp = (
        int(created_at.timestamp() * 1000)
        if created_at is not None
        else int(time.time() * 1000)
    )
    is_call = notification.notification_type in {
        Notification.TYPE_CALL,
        Notification.TYPE_MISSED_CALL,
    }

    return {
        "title": notification.title or "Heartly update",
        "body": (
            notification.message
            or notification_icon(notification.notification_type)
            or "You have a new Heartly update."
        )[:240],
        "url": notification_open_url(notification),
        "tag": notification_dedupe_key(
            notification
        ),
        "icon": "/pwa/icon-192.png",
        "badge": "/pwa/icon-192.png",
        "notification_id": notification.pk,
        "notification_type": notification.notification_type,
        "related_object_type": notification.related_object_type,
        "related_object_id": notification.related_object_id,
        "timestamp": timestamp,
        "require_interaction": is_call,
        "vibrate": (
            [300, 120, 300, 120, 300]
            if is_call
            else [180, 80, 180]
        ),
    }


def notification_ttl(notification):
    if notification.notification_type == Notification.TYPE_CALL:
        return _setting_int(
            "HEARTLY_PUSH_CALL_TTL_SECONDS",
            90,
            minimum=30,
            maximum=600,
        )

    if notification.notification_type in {
        Notification.TYPE_MESSAGE,
        Notification.TYPE_MISSED_CALL,
    }:
        return _setting_int(
            "HEARTLY_PUSH_MESSAGE_TTL_SECONDS",
            7200,
            minimum=300,
            maximum=86400,
        )

    return _setting_int(
        "HEARTLY_PUSH_DEFAULT_TTL_SECONDS",
        86400,
        minimum=300,
        maximum=604800,
    )


def notification_urgency(notification):
    if notification.notification_type in {
        Notification.TYPE_MESSAGE,
        Notification.TYPE_CALL,
        Notification.TYPE_MISSED_CALL,
        Notification.TYPE_MATCH,
    }:
        return "high"
    return "normal"


def notification_topic(notification):
    return notification_dedupe_key(notification)[:32]


def _status_code(exc):
    return getattr(
        getattr(exc, "response", None),
        "status_code",
        None,
    )


def _retryable_status(status_code):
    return (
        status_code is None
        or status_code in {408, 425, 429}
        or (
            isinstance(status_code, int)
            and 500 <= status_code <= 599
        )
    )


def _expired_status(status_code):
    return status_code in {400, 404, 410}


def _deliver_to_subscription(
    *,
    notification,
    subscription,
    payload,
):
    attempts = _setting_int(
        "HEARTLY_PUSH_RETRY_ATTEMPTS",
        2,
        minimum=1,
        maximum=3,
    )
    retry_delay = _setting_float(
        "HEARTLY_PUSH_RETRY_DELAY_SECONDS",
        0.4,
        minimum=0.0,
        maximum=3.0,
    )
    timeout = _setting_int(
        "HEARTLY_PUSH_TIMEOUT_SECONDS",
        8,
        minimum=2,
        maximum=20,
    )

    for attempt in range(1, attempts + 1):
        try:
            webpush(
                subscription_info=subscription.as_webpush_dict(),
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUBJECT},
                ttl=notification_ttl(notification),
                timeout=timeout,
                headers={
                    "Urgency": notification_urgency(notification),
                    "Topic": notification_topic(notification),
                },
            )
            return True
        except WebPushException as exc:
            status_code = _status_code(exc)

            if _expired_status(status_code):
                subscription.delete()
                logger.info(
                    "Removed expired Heartly push subscription %s "
                    "(HTTP %s).",
                    subscription.pk,
                    status_code,
                )
                return False

            if (
                attempt < attempts
                and _retryable_status(status_code)
            ):
                time.sleep(retry_delay * attempt)
                continue

            logger.warning(
                "Heartly push delivery failed for subscription %s "
                "(HTTP %s, attempt %s/%s).",
                subscription.pk,
                status_code or "unknown",
                attempt,
                attempts,
            )
            return False
        except Exception:
            if attempt < attempts:
                time.sleep(retry_delay * attempt)
                continue

            logger.exception(
                "Unexpected Heartly push delivery error for "
                "subscription %s.",
                subscription.pk,
            )
            return False

    return False


def send_notification_push(notification_id):
    if not push_is_configured():
        return 0

    close_old_connections()
    try:
        try:
            notification = Notification.objects.get(
                pk=notification_id,
                is_resolved=False,
            )
        except Notification.DoesNotExist:
            return 0

        subscriptions = list(
            PushSubscription.objects.filter(
                user_id=notification.recipient_id,
                enabled=True,
            )
        )
        if not subscriptions:
            logger.info(
                "Heartly push skipped: user %s has no active "
                "subscription.",
                notification.recipient_id,
            )
            return 0

        payload = json.dumps(
            notification_push_payload(notification),
            separators=(",", ":"),
        )

        delivered = 0
        for subscription in subscriptions:
            if _deliver_to_subscription(
                notification=notification,
                subscription=subscription,
                payload=payload,
            ):
                delivered += 1

        logger.info(
            "Heartly push result: notification=%s "
            "subscriptions=%s delivered=%s",
            notification_id,
            len(subscriptions),
            delivered,
        )
        return delivered
    finally:
        close_old_connections()


def _push_finished(notification_id, future):
    try:
        future.result()
    except Exception:
        logger.exception(
            "Heartly background push worker failed for "
            "notification %s.",
            notification_id,
        )


def enqueue_notification_push(notification_id):
    if not push_is_configured():
        logger.info(
            "Heartly push skipped: VAPID settings are incomplete "
            "for notification %s.",
            notification_id,
        )
        return False

    future = _executor.submit(
        send_notification_push,
        notification_id,
    )
    future.add_done_callback(
        lambda completed, item_id=notification_id: (
            _push_finished(item_id, completed)
        )
    )
    return True
