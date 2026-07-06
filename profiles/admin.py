from django.contrib import admin
from django.utils import timezone

from .models import Interest, Profile, ProfileReport, UserBlock


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "display_name",
        "age",
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

    readonly_fields = (
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

    def hide_profiles(self, request, queryset):
        queryset.update(hidden_by_moderation=True)

    hide_profiles.short_description = "Hide selected profiles from Heartly"

    def restore_profiles(self, request, queryset):
        queryset.update(hidden_by_moderation=False)

    restore_profiles.short_description = "Restore selected profiles to Heartly"


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

    def mark_reviewed(self, request, queryset):
        queryset.update(
            reviewed=True,
            status=ProfileReport.STATUS_REVIEWED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )

    mark_reviewed.short_description = "Mark selected reports as reviewed"

    def mark_actioned(self, request, queryset):
        queryset.update(
            reviewed=True,
            status=ProfileReport.STATUS_ACTIONED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )

    mark_actioned.short_description = "Mark selected reports as actioned"

    def mark_dismissed(self, request, queryset):
        queryset.update(
            reviewed=True,
            status=ProfileReport.STATUS_DISMISSED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )

    mark_dismissed.short_description = "Dismiss selected reports"

    def hide_reported_profiles(self, request, queryset):
        user_ids = queryset.values_list("reported_user_id", flat=True)

        Profile.objects.filter(
            user_id__in=user_ids,
        ).update(
            hidden_by_moderation=True,
        )

        queryset.update(
            reviewed=True,
            status=ProfileReport.STATUS_ACTIONED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )

    hide_reported_profiles.short_description = "Hide profiles from selected reports"

    def restore_reported_profiles(self, request, queryset):
        user_ids = queryset.values_list("reported_user_id", flat=True)

        Profile.objects.filter(
            user_id__in=user_ids,
        ).update(
            hidden_by_moderation=False,
        )

    restore_reported_profiles.short_description = "Restore profiles from selected reports"


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