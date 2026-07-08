from django.contrib import admin

from .models import Comment, Post, PostLike, PostReport


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "has_image", "has_video", "is_hidden", "created_at")
    list_filter = ("is_hidden", "hidden_by_moderation", "created_at")
    search_fields = ("content", "user__username", "user__email")
    readonly_fields = ("created_at", "updated_at", "edited_at")

    def has_image(self, obj):
        return bool(obj.image)

    has_image.boolean = True

    def has_video(self, obj):
        return bool(obj.video)

    has_video.boolean = True


@admin.register(PostLike)
class PostLikeAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "user", "created_at")
    search_fields = ("post__content", "user__username", "user__email")


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "user", "created_at")
    search_fields = ("content", "user__username", "user__email")


@admin.register(PostReport)
class PostReportAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "reporter", "reason", "status", "reviewed", "created_at")
    list_filter = ("reason", "status", "reviewed", "created_at")
    search_fields = ("post__content", "reporter__username", "reporter__email", "details")
