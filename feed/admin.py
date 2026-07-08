from django.contrib import admin

from .models import Comment, Post, PostLike


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "short_content",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "created_at",
        "updated_at",
    )
    search_fields = (
        "content",
        "user__email",
        "user__username",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)

    def short_content(self, obj):
        if not obj.content:
            return "Media post"
        return obj.content[:80]

    short_content.short_description = "Content"


@admin.register(PostLike)
class PostLikeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "post",
        "user",
        "created_at",
    )
    list_filter = (
        "created_at",
    )
    search_fields = (
        "user__email",
        "user__username",
        "post__content",
    )
    ordering = ("-created_at",)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "post",
        "user",
        "short_content",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "created_at",
        "updated_at",
    )
    search_fields = (
        "content",
        "user__email",
        "user__username",
        "post__content",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)

    def short_content(self, obj):
        return obj.content[:80] if obj.content else ""

    short_content.short_description = "Comment"