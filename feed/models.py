from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

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
    hidden_by_moderation = models.BooleanField(
        default=False,
        db_index=True,
    )
    moderation_note = models.TextField(blank=True)
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="moderated_feed_posts",
    )
    moderated_at = models.DateTimeField(blank=True, null=True)

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
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reviewed_feed_post_reports",
    )
    reviewed_at = models.DateTimeField(blank=True, null=True)
    moderator_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("post", "reporter")

    def __str__(self):
        return f"Report on post {self.post_id} by {self.reporter}"

    def set_review_status(self, status, *, moderator=None, note=None):
        if status not in dict(self.STATUS_CHOICES):
            raise ValueError("Invalid post report status.")

        self.status = status
        self.reviewed = status != self.STATUS_PENDING
        self.reviewed_by = moderator if self.reviewed else None
        self.reviewed_at = timezone.now() if self.reviewed else None
        if note is not None:
            self.moderator_note = note
        self.save(
            update_fields=[
                "status",
                "reviewed",
                "reviewed_by",
                "reviewed_at",
                "moderator_note",
            ]
        )


STORY_LIFETIME = timedelta(hours=5)


class StoryQuerySet(models.QuerySet):
    def active(self):
        return self.filter(expires_at__gt=timezone.now())

    def expired(self):
        return self.filter(expires_at__lte=timezone.now())


class Story(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stories",
    )
    caption = models.CharField(max_length=280, blank=True)
    image = models.ImageField(
        upload_to="stories/images/",
        blank=True,
        null=True,
    )

    if VideoMediaCloudinaryStorage:
        video = models.FileField(
            upload_to="stories/videos/",
            blank=True,
            null=True,
            storage=VideoMediaCloudinaryStorage(),
        )
    else:
        video = models.FileField(
            upload_to="stories/videos/",
            blank=True,
            null=True,
        )

    # These values are set together inside save(), guaranteeing that a Story
    # remains active for exactly five hours.
    created_at = models.DateTimeField(editable=False)
    expires_at = models.DateTimeField(editable=False, db_index=True)

    objects = StoryQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["author", "expires_at"],
                name="feed_story_author_exp_idx",
            ),
            models.Index(
                fields=["expires_at", "created_at"],
                name="feed_story_exp_created_idx",
            ),
        ]

    def clean(self):
        super().clean()
        has_image = bool(self.image)
        has_video = bool(self.video)

        if has_image == has_video:
            raise ValidationError("A Story must contain one photo or one video.")

    def save(self, *args, **kwargs):
        if self._state.adding:
            created = timezone.now()
            self.created_at = created
            self.expires_at = created + STORY_LIFETIME

        super().save(*args, **kwargs)

    @property
    def is_active(self):
        return timezone.now() < self.expires_at

    @property
    def is_video(self):
        return bool(self.video)

    @property
    def remaining_seconds(self):
        return max(0, int((self.expires_at - timezone.now()).total_seconds()))

    def __str__(self):
        return f"Story by {self.author} - {self.created_at:%Y-%m-%d %H:%M}"


class StoryReaction(models.Model):
    REACTION_LOVE = "love"
    REACTION_LAUGH = "laugh"
    REACTION_WOW = "wow"

    REACTION_CHOICES = [
        (REACTION_LOVE, "Love"),
        (REACTION_LAUGH, "Laugh"),
        (REACTION_WOW, "Wow"),
    ]

    story = models.ForeignKey(
        Story,
        on_delete=models.CASCADE,
        related_name="reactions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="story_reactions",
    )
    reaction_type = models.CharField(
        max_length=20,
        choices=REACTION_CHOICES,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["story", "user"],
                name=(
                    "unique_story_reaction_per_user"
                ),
            )
        ]
        indexes = [
            models.Index(
                fields=[
                    "story",
                    "reaction_type",
                ],
                name=(
                    "feed_storyr_story_type_idx"
                ),
            ),
            models.Index(
                fields=["user", "updated_at"],
                name=(
                    "feed_storyr_user_time_idx"
                ),
            ),
        ]

    def __str__(self):
        return (
            f"{self.user} reacted "
            f"{self.reaction_type} to "
            f"story {self.story_id}"
        )


class StoryView(models.Model):
    story = models.ForeignKey(
        Story,
        on_delete=models.CASCADE,
        related_name="views",
    )
    viewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="story_views",
    )
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-viewed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["story", "viewer"],
                name="unique_story_view_per_user",
            )
        ]
        indexes = [
            models.Index(
                fields=["story", "viewed_at"],
                name="feed_storyv_story_view_idx",
            ),
            models.Index(
                fields=["viewer", "viewed_at"],
                name="feed_storyv_user_view_idx",
            ),
        ]

    def __str__(self):
        return f"{self.viewer} viewed story {self.story_id}"


@receiver(post_delete, sender=Story)
def remove_story_media(sender, instance, **kwargs):
    """Remove Cloudinary/local media when a Story row is deleted."""
    media_files = []
    for field in (instance.image, instance.video):
        if field and field.name:
            media_files.append((field.storage, field.name))

    for storage, name in media_files:
        def remove_file(file_storage=storage, file_name=name):
            try:
                file_storage.delete(file_name)
            except Exception:
                # Database deletion must still succeed if remote storage is
                # temporarily unavailable. The orphan can be cleaned later.
                pass

        transaction.on_commit(remove_file, robust=True)
