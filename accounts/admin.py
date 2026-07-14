from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser, EmailVerificationCode


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "email",
        "username",
        "full_name",
        "is_staff",
        "is_active",
        "created_at",
    )
    list_filter = ("is_staff", "is_superuser", "is_active", "gender")
    search_fields = ("email", "username", "full_name", "first_name", "last_name")
    ordering = ("-created_at",)
    readonly_fields = ("last_login", "date_joined", "created_at", "updated_at")

    fieldsets = UserAdmin.fieldsets + (
        (
            "Heartly profile",
            {
                "fields": (
                    "full_name",
                    "phone_number",
                    "gender",
                    "interested_in",
                    "date_of_birth",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Heartly account",
            {
                "fields": (
                    "email",
                    "full_name",
                    "phone_number",
                    "gender",
                    "interested_in",
                    "date_of_birth",
                )
            },
        ),
    )


@admin.register(EmailVerificationCode)
class EmailVerificationCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "email", "created_at", "expires_at", "used_at", "attempts")
    list_filter = ("created_at", "expires_at", "used_at")
    search_fields = ("user__email", "user__username", "email")
    readonly_fields = (
        "user",
        "email",
        "code_hash",
        "created_at",
        "expires_at",
        "used_at",
        "attempts",
    )

    def has_add_permission(self, request):
        return False
