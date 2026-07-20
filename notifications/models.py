from django.conf import settings
from django.db import models


class Notification(models.Model):
    TYPE_MESSAGE = "message"
    TYPE_MATCH = "match"
    TYPE_LIKE = "like"
    TYPE_COMMENT = "comment"
    TYPE_CALL = "call"
    TYPE_MISSED_CALL = "missed_call"
    TYPE_REPORT = "report"
    TYPE_SYSTEM = "system"

    # These two values intentionally stay out of TYPE_CHOICES. They are created
    # by Heartly's broadcast views, not by the normal notification admin form.
    # Keeping the database field definition unchanged means this feature does
    # not require a risky migration on the existing Neon database.
    TYPE_BROADCAST = "broadcast"
    TYPE_BROADCAST_FEEDBACK = "broadcast_feedback"

    TYPE_CHOICES = [
        (TYPE_MESSAGE, "Message"),
        (TYPE_MATCH, "Match"),
        (TYPE_LIKE, "Like"),
        (TYPE_COMMENT, "Comment"),
        (TYPE_CALL, "Call"),
        (TYPE_MISSED_CALL, "Missed call"),
        (TYPE_REPORT, "Report"),
        (TYPE_SYSTEM, "System"),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications_sent",
        null=True,
        blank=True,
    )
    notification_type = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES,
        default=TYPE_SYSTEM,
    )
    title = models.CharField(max_length=120)
    message = models.TextField(blank=True)
    url = models.CharField(max_length=500, blank=True)
    related_object_type = models.CharField(max_length=120, blank=True)
    related_object_id = models.PositiveIntegerField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read", "is_resolved"]),
            models.Index(
                fields=["recipient", "is_resolved", "-created_at"],
                name="notify_recipient_recent_idx",
            ),
            models.Index(fields=["notification_type"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.recipient} - {self.title}"


class PushSubscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint = models.TextField(unique=True)
    p256dh = models.TextField()
    auth = models.TextField()
    user_agent = models.CharField(max_length=500, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(
                fields=["user", "enabled"],
                name="notificatio_user_id_8ff346_idx",
            ),
            models.Index(
                fields=["updated_at"],
                name="notificatio_updated_b98f91_idx",
            ),
        ]

    def as_webpush_dict(self):
        return {
            "endpoint": self.endpoint,
            "keys": {"p256dh": self.p256dh, "auth": self.auth},
        }

    def __str__(self):
        return f"{self.user} push subscription"
