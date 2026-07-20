from django.contrib import admin
from django.utils import timezone

from .models import (
    Interest,
    ModerationAction,
    Profile,
    ProfilePhoto,
    ProfileReport,
    UserBlock,
)


def record_actions(rows):
    if rows:
        ModerationAction.objects.bulk_create(
            [ModerationAction(**row) for row in rows]
        )


class ProfilePhotoInline(admin.TabularInline):
    model = ProfilePhoto
    extra = 0
    fields = ("position", "image", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("position", "id")
    max_num = ProfilePhoto.MAX_PHOTOS


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "display_name",
        "age",
        "connection_goal",
        "location",
        "profile_visible",
        "hidden_by_moderation",
        "show_online_status",
        "allow_message_requests",
        "safety_filters_enabled",
        "email_verified",
        "updated_at",
    )

    list_filter = (
        "connection_goal",
        "profile_visible",
        "hidden_by_moderation",
        "show_online_status",
        "allow_message_requests",
        "safety_filters_enabled",
        "email_verified",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "user__username",
        "user__email",
        "display_name",
        "location",
        "bio",
        "moderation_note",
    )

    filter_horizontal = ("interests",)

    inlines = (ProfilePhotoInline,)

    readonly_fields = (
        "hidden_by_moderation",
        "created_at",
        "updated_at",
    )

    actions = (
        "hide_profiles",
        "restore_profiles",
    )

    ordering = ("-updated_at",)

    fieldsets = (
        (
            "User profile",
            {
                "fields": (
                    "user",
                    "display_name",
                    "age",
                    "location",
                    "bio",
                    "gender",
                    "connection_goal",
                    "interested_in",
                    "profile_picture",
                    "interests",
                )
            },
        ),
        (
            "Privacy and safety",
            {
                "fields": (
                    "profile_visible",
                    "show_online_status",
                    "allow_message_requests",
                    "safety_filters_enabled",
                    "email_verified",
                )
            },
        ),
        (
            "Moderation",
            {
                "fields": (
                    "hidden_by_moderation",
                    "moderation_note",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.action(
        description="Hide selected profiles from Heartly",
        permissions=["change"],
    )
    def hide_profiles(self, request, queryset):
        profiles = list(
            queryset.filter(
                hidden_by_moderation=False,
            ).select_related("user")
        )
        Profile.objects.filter(
            id__in=[profile.id for profile in profiles]
        ).update(hidden_by_moderation=True)
        record_actions(
            [
                {
                    "moderator": request.user,
                    "target_user": profile.user,
                    "action": ModerationAction.ACTION_PROFILE_HIDDEN,
                    "source_type": ModerationAction.SOURCE_PROFILE,
                    "source_object_id": profile.id,
                    "note": profile.moderation_note,
                }
                for profile in profiles
            ]
        )

    @admin.action(
        description="Restore selected profiles to Heartly",
        permissions=["change"],
    )
    def restore_profiles(self, request, queryset):
        profiles = list(
            queryset.filter(
                hidden_by_moderation=True,
            ).select_related("user")
        )
        Profile.objects.filter(
            id__in=[profile.id for profile in profiles]
        ).update(hidden_by_moderation=False)
        record_actions(
            [
                {
                    "moderator": request.user,
                    "target_user": profile.user,
                    "action": ModerationAction.ACTION_PROFILE_RESTORED,
                    "source_type": ModerationAction.SOURCE_PROFILE,
                    "source_object_id": profile.id,
                    "note": profile.moderation_note,
                }
                for profile in profiles
            ]
        )


@admin.register(ProfilePhoto)
class ProfilePhotoAdmin(admin.ModelAdmin):
    list_display = ("profile", "position", "created_at", "updated_at")
    list_filter = ("position", "created_at", "updated_at")
    search_fields = ("profile__user__username", "profile__user__email", "profile__display_name")
    ordering = ("profile_id", "position", "id")


@admin.register(Interest)
class InterestAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(ProfileReport)
class ProfileReportAdmin(admin.ModelAdmin):
    list_display = (
        "reported_user",
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
        "reported_user__username",
        "reported_user__email",
        "reporter__username",
        "reporter__email",
        "details",
        "moderator_note",
    )

    readonly_fields = (
        "reported_user",
        "reporter",
        "reason",
        "details",
        "status",
        "reviewed",
        "reviewed_by",
        "reviewed_at",
        "created_at",
    )

    actions = (
        "mark_reviewed",
        "mark_actioned",
        "mark_dismissed",
        "hide_reported_profiles",
        "restore_reported_profiles",
    )

    ordering = ("-created_at",)

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
        now = timezone.now()
        ProfileReport.objects.filter(
            id__in=[report.id for report in reports]
        ).update(
            reviewed=True,
            status=status,
            reviewed_by=request.user,
            reviewed_at=now,
        )
        record_actions(
            [
                {
                    "moderator": request.user,
                    "target_user": report.reported_user,
                    "action": audit_action,
                    "source_type": ModerationAction.SOURCE_PROFILE_REPORT,
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
            status=ProfileReport.STATUS_REVIEWED,
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
            status=ProfileReport.STATUS_ACTIONED,
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
            status=ProfileReport.STATUS_DISMISSED,
            audit_action=(
                ModerationAction.ACTION_REPORT_DISMISSED
            ),
        )

    @admin.action(
        description="Hide profiles from selected reports",
        permissions=["change"],
    )
    def hide_reported_profiles(self, request, queryset):
        reports = list(
            queryset.select_related("reported_user")
        )
        user_ids = {
            report.reported_user_id for report in reports
        }

        Profile.objects.filter(
            user_id__in=user_ids,
        ).update(
            hidden_by_moderation=True,
        )

        ProfileReport.objects.filter(
            id__in=[report.id for report in reports]
        ).update(
            reviewed=True,
            status=ProfileReport.STATUS_ACTIONED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        record_actions(
            [
                {
                    "moderator": request.user,
                    "target_user": report.reported_user,
                    "action": ModerationAction.ACTION_PROFILE_HIDDEN,
                    "source_type": ModerationAction.SOURCE_PROFILE_REPORT,
                    "source_object_id": report.id,
                    "note": report.moderator_note,
                }
                for report in reports
            ]
        )

    @admin.action(
        description="Restore profiles from selected reports",
        permissions=["change"],
    )
    def restore_reported_profiles(self, request, queryset):
        reports = list(
            queryset.select_related("reported_user")
        )
        user_ids = {
            report.reported_user_id for report in reports
        }

        Profile.objects.filter(
            user_id__in=user_ids,
        ).update(
            hidden_by_moderation=False,
        )
        record_actions(
            [
                {
                    "moderator": request.user,
                    "target_user": report.reported_user,
                    "action": ModerationAction.ACTION_PROFILE_RESTORED,
                    "source_type": ModerationAction.SOURCE_PROFILE_REPORT,
                    "source_object_id": report.id,
                    "note": report.moderator_note,
                }
                for report in reports
            ]
        )


@admin.register(ModerationAction)
class ModerationActionAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "action",
        "moderator",
        "target_user",
        "source_type",
        "source_object_id",
    )
    list_filter = (
        "action",
        "source_type",
        "created_at",
    )
    search_fields = (
        "moderator__username",
        "moderator__email",
        "target_user__username",
        "target_user__email",
        "note",
    )
    readonly_fields = (
        "moderator",
        "target_user",
        "action",
        "source_type",
        "source_object_id",
        "note",
        "created_at",
    )
    ordering = ("-created_at", "-id")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserBlock)
class UserBlockAdmin(admin.ModelAdmin):
    list_display = (
        "blocker",
        "blocked",
        "created_at",
    )

    list_filter = ("created_at",)

    search_fields = (
        "blocker__username",
        "blocker__email",
        "blocked__username",
        "blocked__email",
    )

    ordering = ("-created_at",)