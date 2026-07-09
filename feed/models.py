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
        related_name="feed_posts",
    )
    content = models.TextField(blank=True)

    image = models.ImageField(
        upload_to="feed/images/",
        blank=True,
        null=True,
    )

    if VideoMediaCloudinaryStorage:
        video = models.FileField(
            upload_to="feed/videos/",
            blank=True,
            null=True,
            storage=VideoMediaCloudinaryStorage(),
        )
    else:
        video = models.FileField(
            upload_to="feed/videos/",
            blank=True,
            null=True,
        )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    edited_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Post by {self.author} - {self.created_at:%Y-%m-%d %H:%M}"


class PostLike(models.Model):
    REACTION_LIKE = "like"
    REACTION_LOVE = "love"
    REACTION_FUNNY = "funny"
    REACTION_CUTE = "cute"
    REACTION_SUPPORT = "support"
    REACTION_WOW = "wow"

    REACTION_CHOICES = [
        (REACTION_LIKE, "Like"),
        (REACTION_LOVE, "Love"),
        (REACTION_FUNNY, "Funny"),
        (REACTION_CUTE, "Cute"),
        (REACTION_SUPPORT, "Support"),
        (REACTION_WOW, "Wow"),
    ]

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
    reaction_type = models.CharField(
        max_length=20,
        choices=REACTION_CHOICES,
        default=REACTION_LOVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("post", "user")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} reacted {self.reaction_type} to post {self.post_id}"


class PostSave(models.Model):
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="saves",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_feed_posts",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["post", "user"],
                name="unique_saved_feed_post_per_user",
            )
        ]
        indexes = [
            models.Index(fields=["post", "created_at"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"{self.user} saved post {self.post_id}"


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
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="replies",
        blank=True,
        null=True,
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(
        auto_now=True,
        db_column="edited_at",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["post", "parent", "created_at"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        preview = (self.content or "").strip()
        if len(preview) > 48:
            preview = preview[:45] + "..."
        return f"{self.user}: {preview}"

    @property
    def edited_at(self):
        return self.updated_at

    @edited_at.setter
    def edited_at(self, value):
        self.updated_at = value


class CommentReaction(models.Model):
    REACTION_LIKE = "like"
    REACTION_LOVE = "love"
    REACTION_FUNNY = "funny"
    REACTION_CUTE = "cute"
    REACTION_SUPPORT = "support"
    REACTION_WOW = "wow"

    REACTION_CHOICES = [
        (REACTION_LIKE, "Like"),
        (REACTION_LOVE, "Love"),
        (REACTION_FUNNY, "Funny"),
        (REACTION_CUTE, "Cute"),
        (REACTION_SUPPORT, "Support"),
        (REACTION_WOW, "Wow"),
    ]

    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name="reactions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="feed_comment_reactions",
    )
    reaction_type = models.CharField(
        max_length=20,
        choices=REACTION_CHOICES,
        default=REACTION_LOVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("comment", "user")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["comment", "reaction_type"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"{self.user} reacted {self.reaction_type} to comment {self.comment_id}"


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