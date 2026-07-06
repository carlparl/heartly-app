from django.contrib import admin

from .models import HeartlyMessage


@admin.register(HeartlyMessage)
class HeartlyMessageAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "short_text", "created_at")
    list_filter = ("role", "created_at")
    search_fields = ("user__username", "user__email", "text")
    readonly_fields = ("created_at",)

    def short_text(self, obj):
        return obj.text[:60]

    short_text.short_description = "Message"