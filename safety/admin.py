from django.contrib import admin
from django.utils import timezone

from .models import BlockedUser, Report


@admin.register(BlockedUser)
class BlockedUserAdmin(admin.ModelAdmin):
    list_display = [
        "blocker",
        "blocked",
        "reason",
        "created_at",
    ]

    search_fields = [
        "blocker__username",
        "blocker__email",
        "blocked__username",
        "blocked__email",
        "reason",
    ]

    list_filter = [
        "created_at",
    ]

    ordering = [
        "-created_at",
    ]


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = [
        "target_type",
        "reporter",
        "reported_user",
        "reason",
        "status",
        "created_at",
    ]

    list_filter = [
        "target_type",
        "reason",
        "status",
        "created_at",
    ]

    search_fields = [
        "reporter__username",
        "reporter__email",
        "reported_user__username",
        "reported_user__email",
        "details",
    ]

    readonly_fields = [
        "created_at",
        "reviewed_at",
    ]

    actions = [
        "mark_reviewing",
        "mark_resolved",
        "mark_dismissed",
    ]

    ordering = [
        "-created_at",
    ]

    @admin.action(description="Mark selected reports as reviewing")
    def mark_reviewing(self, request, queryset):
        queryset.update(status=Report.STATUS_REVIEWING)

    @admin.action(description="Mark selected reports as resolved")
    def mark_resolved(self, request, queryset):
        queryset.update(
            status=Report.STATUS_RESOLVED,
            reviewed_at=timezone.now(),
        )

    @admin.action(description="Mark selected reports as dismissed")
    def mark_dismissed(self, request, queryset):
        queryset.update(
            status=Report.STATUS_DISMISSED,
            reviewed_at=timezone.now(),
        )