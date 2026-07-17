from django.contrib import admin

from django.utils import timezone

from .models import (
    Comment,
    Post,
    PostLike,
    Story,
    StoryReaction,
    StoryView,
)


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


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "author",
        "media_type",
        "is_active_now",
        "viewer_count",
        "created_at",
        "expires_at",
    )
    list_filter = ("created_at", "expires_at")
    search_fields = ("author__username", "author__email", "caption")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "expires_at")
    list_select_related = ("author",)
    actions = ("delete_expired_stories",)

    @admin.display(description="Media")
    def media_type(self, obj):
        return "Video" if obj.video else "Photo"

    @admin.display(boolean=True, description="Active")
    def is_active_now(self, obj):
        return obj.expires_at > timezone.now()

    @admin.display(description="Views")
    def viewer_count(self, obj):
        return obj.views.exclude(viewer_id=obj.author_id).count()

    @admin.action(description="Delete selected expired Stories")
    def delete_expired_stories(self, request, queryset):
        queryset.filter(expires_at__lte=timezone.now()).delete()


@admin.register(StoryReaction)
class StoryReactionAdmin(admin.ModelAdmin):
    list_display = (
        "story",
        "user",
        "reaction_type",
        "updated_at",
    )
    list_filter = (
        "reaction_type",
        "updated_at",
    )
    search_fields = (
        "story__author__username",
        "story__author__email",
        "user__username",
        "user__email",
    )
    ordering = ("-updated_at",)
    list_select_related = (
        "story",
        "user",
    )
    readonly_fields = (
        "story",
        "user",
        "reaction_type",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False


@admin.register(StoryView)
class StoryViewAdmin(admin.ModelAdmin):
    list_display = ("story", "viewer", "viewed_at")
    list_filter = ("viewed_at",)
    search_fields = (
        "story__author__username",
        "story__author__email",
        "viewer__username",
        "viewer__email",
    )
    ordering = ("-viewed_at",)
    list_select_related = ("story", "viewer")
    readonly_fields = ("story", "viewer", "viewed_at")

    def has_add_permission(self, request):
        return False
