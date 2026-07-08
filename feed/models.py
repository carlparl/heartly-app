
from django.utils import timezone

from django.conf import settings
from django.db import models

try:
    from cloudinary_storage.storage import VideoMediaCloudinaryStorage
except ImportError:
    VideoMediaCloudinaryStorage = None


class Post(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="feed_posts"
    )
    content = models.TextField(blank=True)

    image = models.ImageField(
        upload_to="feed/images/",
        blank=True,
        null=True
    )

    if VideoMediaCloudinaryStorage:
        video = models.FileField(
            upload_to="feed/videos/",
            blank=True,
            null=True,
            storage=VideoMediaCloudinaryStorage()
        )
    else:
        video = models.FileField(
            upload_to="feed/videos/",
            blank=True,
            null=True
        )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    edited_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Post by {self.author} - {self.created_at:%Y-%m-%d %H:%M}"




class PostLike(models.Model):
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="likes",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="feed_likes",
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

    # Existing database column is feed_comment.edited_at.
    # Python code can safely use comment.updated_at.
    updated_at = models.DateTimeField(
        auto_now=True,
        db_column="edited_at",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        preview = (self.content or "").strip()
        if len(preview) > 48:
            preview = preview[:45] + "..."
        return f"{self.user}: {preview}"

    @property
    def edited_at(self):
        """Backward-compatible alias for old templates/admin code."""
        return self.updated_at

    @edited_at.setter
    def edited_at(self, value):
        self.updated_at = value


class PostReport(models.Model):
    REASON_OTHER = "other"
    REASON_SPAM = "spam"
    REASON_HARASSMENT = "harassment"
    REASON_IMPERSONATION = "impersonation"
    REASON_INAPPROPRIATE = "inappropriate"

    REASON_CHOICES = [
        (REASON_OTHER, "Other"),
        (REASON_SPAM, "Spam"),
        (REASON_HARASSMENT, "Harassment"),
        (REASON_IMPERSONATION, "Impersonation"),
        (REASON_INAPPROPRIATE, "Inappropriate content"),
    ]

    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="reports",
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="feed_post_reports",
    )
    reason = models.CharField(max_length=40, choices=REASON_CHOICES, default=REASON_OTHER)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("post", "reporter")

    def __str__(self):
        return f"Report on post {self.post_id} by {self.reporter}"
