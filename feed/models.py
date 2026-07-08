from django.conf import settings
from django.db import models
from django.utils import timezone

from cloudinary_storage.storage import MediaCloudinaryStorage, VideoMediaCloudinaryStorage


class Post(models.Model):
    """
    Heartly feed post.

    Compatibility rules:
    - The database already uses feed_post.user_id, so keep the field name `user`.
    - `author` is provided as a Python alias only, so older code using post.author still works.
    - Images use Cloudinary image storage directly.
    - Videos use Cloudinary video storage directly.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="feed_posts",
    )
    content = models.TextField(blank=True)

    image = models.ImageField(
        upload_to="feed/images/",
        storage=MediaCloudinaryStorage(),
        blank=True,
        null=True,
    )
    video = models.FileField(
        upload_to="feed/videos/",
        storage=VideoMediaCloudinaryStorage(),
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        name = getattr(self.user, "email", None) or getattr(self.user, "username", "User")
        preview = (self.content or "Media post").strip()
        if len(preview) > 48:
            preview = preview[:45] + "..."
        return f"{name}: {preview}"

    @property
    def author(self):
        """Backward-compatible alias for older views/templates."""
        return self.user

    @author.setter
    def author(self, value):
        self.user = value

    @property
    def has_media(self):
        return bool(self.image or self.video)

    @property
    def like_count(self):
        return self.likes.count()

    @property
    def comment_count(self):
        return self.comments.count()

    def mark_edited(self):
        self.edited_at = timezone.now()
        self.save(update_fields=["content", "image", "video", "edited_at", "updated_at"])


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
