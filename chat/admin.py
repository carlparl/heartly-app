from django.contrib import admin
from django.utils import timezone

from profiles.models import ModerationAction, Profile

from .models import Call, ChatAttachment, ChatMessage, ChatReport, ChatThread


def record_actions(rows):
    if rows:
        ModerationAction.objects.bulk_create(
            [ModerationAction(**row) for row in rows]
        )


@admin.register(ChatThread)
class ChatThreadAdmin(admin.ModelAdmin):
    list_display = ("id", "user_one", "user_two", "updated_at")
    search_fields = ("user_one__username", "user_two__username")
    list_filter = ("created_at", "updated_at")
    ordering = ("-updated_at",)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "thread", "sender", "short_text", "is_read", "created_at")
    search_fields = ("sender__username", "text")
    list_filter = ("is_read", "created_at")
    ordering = ("-created_at",)

    def short_text(self, obj):
        if obj.text:
            return obj.text[:60]

        attachment = obj.attachments.first()

        if attachment:
            return f"{attachment.attachment_type}: {attachment.original_filename}"

        return "Media message"


@admin.register(ChatAttachment)
class ChatAttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "attachment_type", "original_filename", "file_size", "created_at")
    search_fields = ("original_filename", "message__text", "message__sender__username")
    list_filter = ("attachment_type", "created_at")
    ordering = ("-created_at",)


@admin.register(ChatReport)
class ChatReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "reporter",
        "reported_user",
        "reason",
        "status",
        "reviewed",
        "created_at",
    )
    search_fields = (
        "reporter__username",
        "reporter__email",
        "reported_user__username",
        "reported_user__email",
        "details",
        "moderator_note",
    )
    list_filter = (
        "reason",
        "status",
        "reviewed",
        "created_at",
    )
    readonly_fields = (
        "thread",
        "reporter",
        "reported_user",
        "reason",
        "details",
        "status",
        "reviewed",
        "reviewed_by",
        "reviewed_at",
        "created_at",
    )
    list_select_related = (
        "thread",
        "reporter",
        "reported_user",
        "reviewed_by",
    )
    ordering = ("-created_at",)
    actions = (
        "mark_reviewed",
        "mark_actioned",
        "mark_dismissed",
        "hide_reported_users",
        "restore_reported_users",
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
            queryset.select_related("reported_user")
        )
        ChatReport.objects.filter(
            id__in=[report.id for report in reports]
        ).update(
            reviewed=True,
            status=status,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        record_actions(
            [
                {
                    "moderator": request.user,
                    "target_user": report.reported_user,
                    "action": audit_action,
                    "source_type": ModerationAction.SOURCE_CHAT_REPORT,
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
            status=ChatReport.STATUS_REVIEWED,
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
            status=ChatReport.STATUS_ACTIONED,
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
            status=ChatReport.STATUS_DISMISSED,
            audit_action=(
                ModerationAction.ACTION_REPORT_DISMISSED
            ),
        )

    @admin.action(
        description="Hide selected reported users",
        permissions=["change"],
    )
    def hide_reported_users(self, request, queryset):
        reports = list(
            queryset.select_related("reported_user")
        )
        Profile.objects.filter(
            user_id__in={
                report.reported_user_id for report in reports
            }
        ).update(hidden_by_moderation=True)
        ChatReport.objects.filter(
            id__in=[report.id for report in reports]
        ).update(
            reviewed=True,
            status=ChatReport.STATUS_ACTIONED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        record_actions(
            [
                {
                    "moderator": request.user,
                    "target_user": report.reported_user,
                    "action": ModerationAction.ACTION_PROFILE_HIDDEN,
                    "source_type": ModerationAction.SOURCE_CHAT_REPORT,
                    "source_object_id": report.id,
                    "note": report.moderator_note,
                }
                for report in reports
            ]
        )

    @admin.action(
        description="Restore selected reported users",
        permissions=["change"],
    )
    def restore_reported_users(self, request, queryset):
        reports = list(
            queryset.select_related("reported_user")
        )
        Profile.objects.filter(
            user_id__in={
                report.reported_user_id for report in reports
            }
        ).update(hidden_by_moderation=False)
        record_actions(
            [
                {
                    "moderator": request.user,
                    "target_user": report.reported_user,
                    "action": ModerationAction.ACTION_PROFILE_RESTORED,
                    "source_type": ModerationAction.SOURCE_CHAT_REPORT,
                    "source_object_id": report.id,
                    "note": report.moderator_note,
                }
                for report in reports
            ]
        )


@admin.register(Call)
class CallAdmin(admin.ModelAdmin):
    list_display = ("id", "caller", "receiver", "call_type", "status", "started_at", "ended_at")
    search_fields = ("caller__username", "receiver__username")
    list_filter = ("call_type", "status", "started_at")
    ordering = ("-started_at",)