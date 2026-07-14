from django import forms
from django.contrib import admin

from .models import Notification, PushSubscription


class NotificationAdminForm(forms.ModelForm):
    notification_type = forms.ChoiceField(
        choices=[
            *Notification.TYPE_CHOICES,
            (Notification.TYPE_BROADCAST, "Broadcast"),
            (Notification.TYPE_BROADCAST_FEEDBACK, "Broadcast feedback"),
        ]
    )

    class Meta:
        model = Notification
        fields = "__all__"


class NotificationTypeFilter(admin.SimpleListFilter):
    title = "notification type"
    parameter_name = "notification_type"

    def lookups(self, request, model_admin):
        return [
            *Notification.TYPE_CHOICES,
            (Notification.TYPE_BROADCAST, "Broadcast"),
            (Notification.TYPE_BROADCAST_FEEDBACK, "Broadcast feedback"),
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(notification_type=self.value())
        return queryset


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    form = NotificationAdminForm
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
        NotificationTypeFilter,
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
    list_select_related = ("recipient", "actor")
    actions = ("mark_selected_read", "resolve_selected")

    @admin.action(description="Mark selected notifications as read")
    def mark_selected_read(self, request, queryset):
        queryset.update(is_read=True)

    @admin.action(description="Resolve selected notifications")
    def resolve_selected(self, request, queryset):
        queryset.update(is_read=True, is_resolved=True)


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "enabled", "updated_at", "created_at")
    list_filter = ("enabled", "created_at", "updated_at")
    search_fields = ("user__username", "user__email", "endpoint")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-updated_at",)
