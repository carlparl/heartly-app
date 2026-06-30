from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class BlockedUser(models.Model):
    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="users_blocked",
    )

    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocked_by_users",
    )

    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["blocker", "blocked"],
                name="unique_blocked_user_pair",
            )
        ]

    def clean(self):
        if self.blocker_id and self.blocked_id and self.blocker_id == self.blocked_id:
            raise ValidationError("You cannot block yourself.")

    def __str__(self):
        return f"{self.blocker} blocked {self.blocked}"


class Report(models.Model):
    TARGET_USER = "user"
    TARGET_POST = "post"
    TARGET_COMMENT = "comment"

    TARGET_TYPE_CHOICES = [
        (TARGET_USER, "User"),
        (TARGET_POST, "Post"),
        (TARGET_COMMENT, "Comment"),
    ]

    REASON_SPAM = "spam"
    REASON_HARASSMENT = "harassment"
    REASON_FAKE = "fake_profile"
    REASON_UNSAFE = "unsafe_behavior"
    REASON_INAPPROPRIATE = "inappropriate_content"
    REASON_OTHER = "other"

    REASON_CHOICES = [
        (REASON_SPAM, "Spam"),
        (REASON_HARASSMENT, "Harassment"),
        (REASON_FAKE, "Fake profile"),
        (REASON_UNSAFE, "Unsafe behavior"),
        (REASON_INAPPROPRIATE, "Inappropriate content"),
        (REASON_OTHER, "Other"),
    ]

    STATUS_OPEN = "open"
    STATUS_REVIEWING = "reviewing"
    STATUS_RESOLVED = "resolved"
    STATUS_DISMISSED = "dismissed"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_REVIEWING, "Reviewing"),
        (STATUS_RESOLVED, "Resolved"),
        (STATUS_DISMISSED, "Dismissed"),
    ]

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports_made",
    )

    target_type = models.CharField(
        max_length=20,
        choices=TARGET_TYPE_CHOICES,
    )

    reported_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports_received",
        blank=True,
        null=True,
    )

    post = models.ForeignKey(
        "feed.Post",
        on_delete=models.CASCADE,
        related_name="reports",
        blank=True,
        null=True,
    )

    comment = models.ForeignKey(
        "feed.Comment",
        on_delete=models.CASCADE,
        related_name="reports",
        blank=True,
        null=True,
    )

    reason = models.CharField(
        max_length=40,
        choices=REASON_CHOICES,
        default=REASON_OTHER,
    )

    details = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.target_type == self.TARGET_USER and not self.reported_user:
            raise ValidationError("A user report needs a reported user.")

        if self.target_type == self.TARGET_POST and not self.post:
            raise ValidationError("A post report needs a post.")

        if self.target_type == self.TARGET_COMMENT and not self.comment:
            raise ValidationError("A comment report needs a comment.")

        if self.reporter_id and self.reported_user_id and self.reporter_id == self.reported_user_id:
            raise ValidationError("You cannot report yourself.")

    def __str__(self):
        return f"{self.get_target_type_display()} report by {self.reporter}"