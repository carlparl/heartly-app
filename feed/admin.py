from django.contrib import admin
from django.db.models import Q
from django.utils import timezone

from notifications.models import Notification
from notifications.activity import (
    resolve_moderation_report_notifications,
)
from profiles.models import ModerationAction

from .models import (
    Comment,
    Post,
    PostLike,
    PostReport,
    Story,
    StoryReaction,
    StoryView,
)


def record_actions(rows):
    if rows:
        ModerationAction.objects.bulk_create(
            [ModerationAction(**row) for row in rows]
        )


def resolve_post_notifications(post_ids):
    post_ids = list(post_ids)
    if not post_ids:
        return 0

    comment_ids = list(
        Comment.objects.filter(
            post_id__in=post_ids,
        ).values_list("id", flat=True)
    )
    return Notification.objects.filter(
        Q(
            related_object_type="feed.post",
            related_object_id__in=post_ids,
        )
        | Q(
            related_object_type__in=[
                "feed.comment",
                "feed.comment_reply",
            ],
            related_object_id__in=comment_ids,
        )
    ).update(
        is_read=True,
        is_resolved=True,
        updated_at=timezone.now(),
    )


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "posted_by",
        "short_content",
        "has_image",
        "has_video",
        "hidden_by_moderation",
    )
    list_filter = (
        "hidden_by_moderation",
        "created_at",
    )
    search_fields = (
        "author__username",
        "author__email",
        "content",
        "moderation_note",
    )
    readonly_fields = (
        "hidden_by_moderation",
        "moderated_by",
        "moderated_at",
    )
    actions = (
        "hide_posts",
        "restore_posts",
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

    @admin.action(
        description="Hide selected posts from Heartly",
        permissions=["change"],
    )
    def hide_posts(self, request, queryset):
        posts = list(
            queryset.filter(
                hidden_by_moderation=False,
            ).select_related("author")
        )
        post_ids = [post.id for post in posts]
        Post.objects.filter(id__in=post_ids).update(
            hidden_by_moderation=True,
            moderated_by=request.user,
            moderated_at=timezone.now(),
        )
        resolve_post_notifications(post_ids)
        record_actions(
            [
                {
                    "moderator": request.user,
                    "target_user": post.author,
                    "action": ModerationAction.ACTION_POST_HIDDEN,
                    "source_type": ModerationAction.SOURCE_POST,
                    "source_object_id": post.id,
                    "note": post.moderation_note,
                }
                for post in posts
            ]
        )

    @admin.action(
        description="Restore selected posts to Heartly",
        permissions=["change"],
    )
    def restore_posts(self, request, queryset):
        posts = list(
            queryset.filter(
                hidden_by_moderation=True,
            ).select_related("author")
        )
        Post.objects.filter(
            id__in=[post.id for post in posts]
        ).update(
            hidden_by_moderation=False,
            moderated_by=request.user,
            moderated_at=timezone.now(),
        )
        record_actions(
            [
                {
                    "moderator": request.user,
                    "target_user": post.author,
                    "action": ModerationAction.ACTION_POST_RESTORED,
                    "source_type": ModerationAction.SOURCE_POST,
                    "source_object_id": post.id,
                    "note": post.moderation_note,
                }
                for post in posts
            ]
        )


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


@admin.register(PostReport)
class PostReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "post",
        "reporter",
        "reason",
        "status",
        "reviewed",
        "created_at",
    )
    list_filter = (
        "reason",
        "status",
        "reviewed",
        "created_at",
    )
    search_fields = (
        "post__author__username",
        "post__author__email",
        "reporter__username",
        "reporter__email",
        "post__content",
        "details",
        "moderator_note",
    )
    readonly_fields = (
        "post",
        "reporter",
        "reason",
        "details",
        "evidence_snapshot",
        "status",
        "reviewed",
        "reviewed_by",
        "reviewed_at",
        "created_at",
    )
    list_select_related = (
        "post",
        "post__author",
        "reporter",
    )
    ordering = ("-created_at",)
    actions = (
        "mark_reviewed",
        "mark_actioned",
        "mark_dismissed",
        "hide_reported_posts",
        "restore_reported_posts",
    )

    def set_report_status(
        self,
        request,
        queryset,
        *,
        status,
        audit_action,
    ):
        reports = list(
            queryset.select_related("post__author")
        )
        PostReport.objects.filter(
            id__in=[report.id for report in reports]
        ).update(
            reviewed=True,
            status=status,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        resolve_moderation_report_notifications(
            "feed.postreport",
            [report.id for report in reports],
        )
        record_actions(
            [
                {
                    "moderator": request.user,
                    "target_user": report.post.author,
                    "action": audit_action,
                    "source_type": ModerationAction.SOURCE_POST_REPORT,
                    "source_object_id": report.id,
                    "note": report.moderator_note,
                }
                for report in reports
            ]
        )

    @admin.action(
        description="Mark selected reports as reviewed",
        permissions=["change"],
    )
    def mark_reviewed(self, request, queryset):
        self.set_report_status(
            request,
            queryset,
            status=PostReport.STATUS_REVIEWED,
            audit_action=(
                ModerationAction.ACTION_REPORT_REVIEWED
            ),
        )

    @admin.action(
        description="Mark selected reports as actioned",
        permissions=["change"],
    )
    def mark_actioned(self, request, queryset):
        self.set_report_status(
            request,
            queryset,
            status=PostReport.STATUS_ACTIONED,
            audit_action=(
                ModerationAction.ACTION_REPORT_ACTIONED
            ),
        )

    @admin.action(
        description="Dismiss selected reports",
        permissions=["change"],
    )
    def mark_dismissed(self, request, queryset):
        self.set_report_status(
            request,
            queryset,
            status=PostReport.STATUS_DISMISSED,
            audit_action=(
                ModerationAction.ACTION_REPORT_DISMISSED
            ),
        )

    @admin.action(
        description="Hide posts from selected reports",
        permissions=["change"],
    )
    def hide_reported_posts(self, request, queryset):
        reports = list(
            queryset.select_related("post__author")
        )
        post_ids = {report.post_id for report in reports}
        Post.objects.filter(id__in=post_ids).update(
            hidden_by_moderation=True,
            moderated_by=request.user,
            moderated_at=timezone.now(),
        )
        PostReport.objects.filter(
            id__in=[report.id for report in reports]
        ).update(
            reviewed=True,
            status=PostReport.STATUS_ACTIONED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        resolve_moderation_report_notifications(
            "feed.postreport",
            [report.id for report in reports],
        )
        resolve_post_notifications(post_ids)
        record_actions(
            [
                {
                    "moderator": request.user,
                    "target_user": report.post.author,
                    "action": ModerationAction.ACTION_POST_HIDDEN,
                    "source_type": ModerationAction.SOURCE_POST_REPORT,
                    "source_object_id": report.id,
                    "note": report.moderator_note,
                }
                for report in reports
            ]
        )

    @admin.action(
        description="Restore posts from selected reports",
        permissions=["change"],
    )
    def restore_reported_posts(self, request, queryset):
        reports = list(
            queryset.select_related("post__author")
        )
        Post.objects.filter(
            id__in={report.post_id for report in reports}
        ).update(
            hidden_by_moderation=False,
            moderated_by=request.user,
            moderated_at=timezone.now(),
        )
        record_actions(
            [
                {
                    "moderator": request.user,
                    "target_user": report.post.author,
                    "action": ModerationAction.ACTION_POST_RESTORED,
                    "source_type": ModerationAction.SOURCE_POST_REPORT,
                    "source_object_id": report.id,
                    "note": report.moderator_note,
                }
                for report in reports
            ]
        )


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
