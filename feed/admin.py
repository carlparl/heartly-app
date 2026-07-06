from django.contrib import admin
from django.contrib import messages

from profiles.models import Profile

from .models import Comment, Post, PostLike, PostReport


def model_has_field(model, field_name):
    return any(field.name == field_name for field in model._meta.fields)


@admin.action(description="Mark selected reports as reviewed")
def mark_reports_reviewed(modeladmin, request, queryset):
    if model_has_field(PostReport, "reviewed"):
        queryset.update(reviewed=True)
        messages.success(request, "Selected reports marked as reviewed.")
    else:
        messages.warning(request, "PostReport has no reviewed field.")


@admin.action(description="Hide authors of selected reported posts")
def hide_reported_post_authors(modeladmin, request, queryset):
    if not model_has_field(Profile, "hidden_by_moderation"):
        messages.warning(request, "Profile has no hidden_by_moderation field.")
        return

    author_ids = queryset.values_list("post__user_id", flat=True).distinct()

    updated = Profile.objects.filter(
        user_id__in=author_ids,
    ).update(
        hidden_by_moderation=True,
    )

    messages.success(request, f"{updated} profile(s) hidden by moderation.")


@admin.action(description="Delete selected reported posts")
def delete_reported_posts(modeladmin, request, queryset):
    post_ids = queryset.values_list("post_id", flat=True).distinct()
    deleted_count, deleted_data = Post.objects.filter(id__in=post_ids).delete()

    if model_has_field(PostReport, "reviewed"):
        queryset.update(reviewed=True)

    messages.success(request, f"Deleted reported post data: {deleted_count} item(s).")


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "short_content", "likes_count", "comments_count", "created_at")
    search_fields = ("user__username", "content")
    list_filter = ("created_at",)
    ordering = ("-created_at",)

    def short_content(self, obj):
        return obj.content[:80] if obj.content else "Media post"

    def likes_count(self, obj):
        return obj.likes.count()

    def comments_count(self, obj):
        return obj.comments.count()


@admin.register(PostLike)
class PostLikeAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "user", "created_at")
    search_fields = ("user__username", "post__content")
    list_filter = ("created_at",)
    ordering = ("-created_at",)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "user", "short_content", "created_at")
    search_fields = ("user__username", "content")
    list_filter = ("created_at",)
    ordering = ("-created_at",)

    def short_content(self, obj):
        return obj.content[:80]


@admin.register(PostReport)
class PostReportAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "reporter", "reason", "review_status", "created_at")
    search_fields = ("reporter__username", "post__content", "details")
    list_filter = ("reason", "created_at")
    ordering = ("-created_at",)
    actions = [
        mark_reports_reviewed,
        hide_reported_post_authors,
        delete_reported_posts,
    ]

    def review_status(self, obj):
        return "Reviewed" if getattr(obj, "reviewed", False) else "Pending"