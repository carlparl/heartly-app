from django.conf import settings
from django.db import models


class Post(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="heartly_posts",
    )

    content = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    edited_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        if self.content:
            return f"{self.user} - {self.content[:40]}"
        return f"{self.user} - post {self.id}"


class PostMedia(models.Model):
    IMAGE = "image"
    VIDEO = "video"

    MEDIA_TYPES = [
        (IMAGE, "Image"),
        (VIDEO, "Video"),
    ]

    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="media",
    )

    media_type = models.CharField(
        max_length=10,
        choices=MEDIA_TYPES,
    )

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

    alt_text = models.CharField(
        max_length=420,
        blank=True,
    )

    order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "created_at"]

    def __str__(self):
        return f"{self.media_type} for post {self.post_id}"


class PostLike(models.Model):
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="likes",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="heartly_post_likes",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["post", "user"],
                name="unique_heartly_post_like",
            )
        ]

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
        related_name="heartly_post_comments",
    )

    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user} - {self.text[:40]}"