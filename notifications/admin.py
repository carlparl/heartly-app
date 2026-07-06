from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "recipient",
        "actor",
        "notification_type",
        "is_read",
        "is_resolved",
        "created_at",
    )

    list_filter = (
        "notification_type",
        "is_read",
        "is_resolved",
        "created_at",
    )

    search_fields = (
        "title",
        "message",
        "recipient__username",
        "recipient__email",
        "actor__username",
        "actor__email",
    )

    ordering = ("-created_at",)