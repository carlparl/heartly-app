from django.conf import settings
from django.db import models
from django.utils import timezone


class Post(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="feed_posts",
    )

    content = models.TextField(blank=True)

    image = models.ImageField(
        upload_to="feed/images/",
        blank=True,
        null=True,
    )

    video = models.FileField(
        upload_to="feed/videos/",
        blank=True,
        null=True,
    )

    # Keep both flags because older parts of Heartly may still reference them.
    hidden_by_moderation = models.BooleanField(default=False)
    is_hidden = models.BooleanField(default=False)
    hidden_at = models.DateTimeField(blank=True, null=True)
    hidden_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="hidden_feed_posts",
    )
    moderation_note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    edited_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        if self.content:
            return f"{self.user} - {self.content[:40]}"
        return f"{self.user} - media post"

    def hide(self, moderator=None, note=""):
        self.is_hidden = True
        self.hidden_by_moderation = True
        self.hidden_at = timezone.now()
        self.hidden_by = moderator
        self.moderation_note = note
        self.save(
            update_fields=[
                "is_hidden",
                "hidden_by_moderation",
                "hidden_at",
                "hidden_by",
                "moderation_note",
            ]
        )

    def unhide(self):
        self.is_hidden = False
        self.hidden_by_moderation = False
        self.hidden_at = None
        self.hidden_by = None
        self.moderation_note = ""
        self.save(
            update_fields=[
                "is_hidden",
                "hidden_by_moderation",
                "hidden_at",
                "hidden_by",
                "moderation_note",
            ]
        )


class PostLike(models.Model):
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="likes",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="post_likes",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("post", "user")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} liked post {self.post_id}"


class Comment(models.Model):
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="comments",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="feed_comments",
    )

    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user} on post {self.post_id}"


class PostReport(models.Model):
    REASON_SPAM = "spam"
    REASON_HARASSMENT = "harassment"
    REASON_INAPPROPRIATE = "inappropriate"
    REASON_FAKE = "fake"
    REASON_OTHER = "other"

    REASON_CHOICES = [
        (REASON_SPAM, "Spam or misleading"),
        (REASON_HARASSMENT, "Harassment or bullying"),
        (REASON_INAPPROPRIATE, "Inappropriate content"),
        (REASON_FAKE, "Fake profile or scam"),
        (REASON_OTHER, "Other"),
    ]

    STATUS_PENDING = "pending"
    STATUS_REVIEWED = "reviewed"
    STATUS_ACTIONED = "actioned"
    STATUS_DISMISSED = "dismissed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_REVIEWED, "Reviewed"),
        (STATUS_ACTIONED, "Action taken"),
        (STATUS_DISMISSED, "Dismissed"),
    ]

    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="feed_reports",
        related_query_name="feed_report",
    )

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submitted_feed_reports",
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
        default=STATUS_PENDING,
    )

    reviewed = models.BooleanField(default=False)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reviewed_feed_reports",
    )

    reviewed_at = models.DateTimeField(blank=True, null=True)
    moderator_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("post", "reporter")

    def __str__(self):
        return f"{self.reporter} reported post {self.post_id}"

    def mark_reviewed(self, moderator=None, note=""):
        self.reviewed = True
        self.status = self.STATUS_REVIEWED
        self.reviewed_by = moderator
        self.reviewed_at = timezone.now()
        self.moderator_note = note
        self.save(
            update_fields=[
                "reviewed",
                "status",
                "reviewed_by",
                "reviewed_at",
                "moderator_note",
            ]
        )

    def mark_actioned(self, moderator=None, note=""):
        self.reviewed = True
        self.status = self.STATUS_ACTIONED
        self.reviewed_by = moderator
        self.reviewed_at = timezone.now()
        self.moderator_note = note
        self.save(
            update_fields=[
                "reviewed",
                "status",
                "reviewed_by",
                "reviewed_at",
                "moderator_note",
            ]
        )

    def dismiss(self, moderator=None, note=""):
        self.reviewed = True
        self.status = self.STATUS_DISMISSED
        self.reviewed_by = moderator
        self.reviewed_at = timezone.now()
        self.moderator_note = note
        self.save(
            update_fields=[
                "reviewed",
                "status",
                "reviewed_by",
                "reviewed_at",
                "moderator_note",
            ]
        )
