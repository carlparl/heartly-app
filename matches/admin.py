from django.contrib import admin

from .models import MatchAction, MutualMatch


@admin.register(MatchAction)
class MatchActionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "from_user",
        "action",
        "to_user",
        "created_at",
    )
    search_fields = (
        "from_user__username",
        "from_user__email",
        "to_user__username",
        "to_user__email",
    )
    list_filter = (
        "action",
        "created_at",
    )
    ordering = ("-created_at",)


@admin.register(MutualMatch)
class MutualMatchAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_one",
        "user_two",
        "created_at",
    )
    search_fields = (
        "user_one__username",
        "user_one__email",
        "user_two__username",
        "user_two__email",
    )
    list_filter = (
        "created_at",
    )
    ordering = ("-created_at",)