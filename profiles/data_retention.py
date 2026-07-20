from datetime import timedelta

from django.conf import settings
from django.contrib.sessions.models import Session
from django.db.models import Q
from django.utils import timezone

from accounts.models import EmailVerificationCode
from notifications.models import Notification, PushSubscription


PRESERVED_SAFETY_MODELS = (
    "profiles.ProfileReport",
    "feed.PostReport",
    "chat.ChatReport",
    "profiles.ModerationAction",
)


def retention_querysets(now=None):
    now = now or timezone.now()
    email_cutoff = now - timedelta(
        days=settings.HEARTLY_RETENTION_EMAIL_CODE_DAYS
    )
    notification_cutoff = now - timedelta(
        days=(
            settings.HEARTLY_RETENTION_RESOLVED_NOTIFICATION_DAYS
        )
    )
    push_cutoff = now - timedelta(
        days=settings.HEARTLY_RETENTION_DISABLED_PUSH_DAYS
    )

    return {
        "expired_email_codes": (
            EmailVerificationCode.objects.filter(
                created_at__lt=email_cutoff,
            ).filter(
                Q(used_at__isnull=False)
                | Q(expires_at__lte=now)
            )
        ),
        "resolved_notifications": (
            Notification.objects.filter(
                is_resolved=True,
                updated_at__lt=notification_cutoff,
            )
        ),
        "disabled_push_subscriptions": (
            PushSubscription.objects.filter(
                enabled=False,
                updated_at__lt=push_cutoff,
            )
        ),
        "expired_sessions": Session.objects.filter(
            expire_date__lte=now,
        ),
    }


def retention_summary(now=None):
    querysets = retention_querysets(now)
    due = {
        name: queryset.count()
        for name, queryset in querysets.items()
    }
    return {
        "due": due,
        "total_due": sum(due.values()),
        "preserved_safety_models": PRESERVED_SAFETY_MODELS,
    }
