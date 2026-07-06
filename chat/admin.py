from django.contrib import admin
from django.contrib import messages

from profiles.models import Profile

from .models import Call, ChatAttachment, ChatMessage, ChatReport, ChatThread


def model_has_field(model, field_name):
    return any(field.name == field_name for field in model._meta.fields)


@admin.action(description="Hide selected reported users")
def hide_reported_users(modeladmin, request, queryset):
    if not model_has_field(Profile, "hidden_by_moderation"):
        messages.warning(request, "Profile has no hidden_by_moderation field.")
        return

    user_ids = queryset.values_list("reported_user_id", flat=True).distinct()

    updated = Profile.objects.filter(
        user_id__in=user_ids,
    ).update(
        hidden_by_moderation=True,
    )

    messages.success(request, f"{updated} reported profile(s) hidden by moderation.")


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
    list_display = ("id", "reporter", "reported_user", "reason", "created_at")
    search_fields = ("reporter__username", "reported_user__username", "details")
    list_filter = ("reason", "created_at")
    ordering = ("-created_at",)
    actions = [hide_reported_users]


@admin.register(Call)
class CallAdmin(admin.ModelAdmin):
    list_display = ("id", "caller", "receiver", "call_type", "status", "started_at", "ended_at")
    search_fields = ("caller__username", "receiver__username")
    list_filter = ("call_type", "status", "started_at")
    ordering = ("-started_at",)