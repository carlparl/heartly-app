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
            models.Index(fields=["notification_type"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.recipient} - {self.title}"
