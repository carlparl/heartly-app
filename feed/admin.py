from django.contrib import admin

from .models import Comment, Post, PostLike


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "posted_by",
        "short_content",
        "has_image",
        "has_video",
    )
    ordering = ("-id",)

    def posted_by(self, obj):
        return (
            getattr(obj, "user", None)
            or getattr(obj, "author", None)
            or "Unknown"
        )

    posted_by.short_description = "User"

    def short_content(self, obj):
        content = getattr(obj, "content", "") or ""
        return content[:60] + "..." if len(content) > 60 else content

    short_content.short_description = "Content"

    def has_image(self, obj):
        return bool(getattr(obj, "image", None))

    has_image.boolean = True
    has_image.short_description = "Image"

    def has_video(self, obj):
        return bool(getattr(obj, "video", None))

    has_video.boolean = True
    has_video.short_description = "Video"


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "post",
        "commented_by",
        "short_content",
    )
    ordering = ("-id",)

    def commented_by(self, obj):
        return getattr(obj, "user", None) or "Unknown"

    commented_by.short_description = "User"

    def short_content(self, obj):
        content = getattr(obj, "content", "") or ""
        return content[:60] + "..." if len(content) > 60 else content

    short_content.short_description = "Content"


@admin.register(PostLike)
class PostLikeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "post",
        "liked_by",
    )
    ordering = ("-id",)

    def liked_by(self, obj):
        return getattr(obj, "user", None) or "Unknown"

    liked_by.short_description = "User"