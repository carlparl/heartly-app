from django.contrib import admin

from .models import Comment, Post, PostLike, PostMedia


class PostMediaInline(admin.TabularInline):
    model = PostMedia
    extra = 0
    fields = (
        "media_type",
        "image",
        "video",
        "alt_text",
        "order",
    )
    ordering = ("order", "created_at")


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "short_content",
        "media_count",
        "created_at",
        "edited_at",
    )
    search_fields = (
        "content",
        "user__username",
        "user__email",
    )
    list_filter = (
        "created_at",
        "edited_at",
    )
    ordering = ("-created_at",)
    inlines = [PostMediaInline]

    def short_content(self, obj):
        if obj.content:
            return obj.content[:50]
        return "Media post"

    short_content.short_description = "Content"

    def media_count(self, obj):
        return obj.media.count()

    media_count.short_description = "Media"


@admin.register(PostMedia)
class PostMediaAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "post",
        "media_type",
        "order",
        "created_at",
    )
    search_fields = (
        "post__content",
        "alt_text",
    )
    list_filter = (
        "media_type",
        "created_at",
    )
    ordering = (
        "post",
        "order",
    )


@admin.register(PostLike)
class PostLikeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "post",
        "user",
        "created_at",
    )
    search_fields = (
        "user__username",
        "user__email",
        "post__content",
    )
    list_filter = (
        "created_at",
    )
    ordering = ("-created_at",)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "post",
        "user",
        "short_text",
        "created_at",
    )
    search_fields = (
        "text",
        "user__username",
        "user__email",
        "post__content",
    )
    list_filter = (
        "created_at",
    )
    ordering = ("-created_at",)

    def short_text(self, obj):
        return obj.text[:50]

    short_text.short_description = "Comment"