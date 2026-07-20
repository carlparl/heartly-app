from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils import timezone

from profiles.models import ModerationAction, Profile

from .models import CustomUser, EmailVerificationCode


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "email",
        "username",
        "full_name",
        "is_staff",
        "is_active",
        "moderation_status",
        "moderation_expires_at",
        "created_at",
    )
    list_filter = (
        "moderation_status",
        "is_staff",
        "is_superuser",
        "is_active",
        "gender",
    )
    search_fields = ("email", "username", "full_name", "first_name", "last_name")
    ordering = ("-created_at",)
    readonly_fields = (
        "last_login",
        "date_joined",
        "moderation_status",
        "moderation_reason",
        "moderation_expires_at",
        "moderation_updated_at",
        "moderation_updated_by",
        "created_at",
        "updated_at",
    )

    actions = (
        "suspend_accounts_for_seven_days",
        "ban_accounts",
        "restore_account_access",
    )

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
        (
            "Moderation",
            {
                "fields": (
                    "moderation_status",
                    "moderation_reason",
                    "moderation_expires_at",
                    "moderation_updated_at",
                    "moderation_updated_by",
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

    def _eligible_accounts(self, request, queryset):
        return list(
            queryset.filter(
                is_staff=False,
                is_superuser=False,
            ).exclude(pk=request.user.pk)
        )

    def _record_account_actions(
        self,
        request,
        users,
        *,
        action,
        note,
    ):
        ModerationAction.objects.bulk_create(
            [
                ModerationAction(
                    moderator=request.user,
                    target_user=user,
                    action=action,
                    source_type=(
                        ModerationAction.SOURCE_ACCOUNT
                    ),
                    source_object_id=user.id,
                    note=note,
                )
                for user in users
            ]
        )

    @admin.action(
        description="Suspend selected accounts for seven days",
        permissions=["change"],
    )
    def suspend_accounts_for_seven_days(
        self,
        request,
        queryset,
    ):
        users = [
            user
            for user in self._eligible_accounts(request, queryset)
            if user.moderation_status
            not in {
                self.model.MODERATION_SUSPENDED,
                self.model.MODERATION_BANNED,
            }
        ]
        now = timezone.now()
        expires_at = now + timedelta(days=7)
        self.model.objects.filter(
            id__in=[user.id for user in users]
        ).update(
            moderation_status=(
                self.model.MODERATION_SUSPENDED
            ),
            moderation_reason="Seven-day staff suspension.",
            moderation_expires_at=expires_at,
            moderation_updated_at=now,
            moderation_updated_by=request.user,
        )
        Profile.objects.filter(
            user_id__in=[user.id for user in users]
        ).update(hidden_by_moderation=True)
        self._record_account_actions(
            request,
            users,
            action=ModerationAction.ACTION_ACCOUNT_SUSPENDED,
            note="Seven-day staff suspension.",
        )
        self.message_user(
            request,
            f"Suspended {len(users)} account(s).",
        )

    @admin.action(
        description="Permanently ban selected accounts",
        permissions=["change"],
    )
    def ban_accounts(self, request, queryset):
        users = [
            user
            for user in self._eligible_accounts(request, queryset)
            if user.moderation_status
            != self.model.MODERATION_BANNED
        ]
        now = timezone.now()
        self.model.objects.filter(
            id__in=[user.id for user in users]
        ).update(
            moderation_status=self.model.MODERATION_BANNED,
            moderation_reason="Permanent staff ban.",
            moderation_expires_at=None,
            moderation_updated_at=now,
            moderation_updated_by=request.user,
        )
        Profile.objects.filter(
            user_id__in=[user.id for user in users]
        ).update(hidden_by_moderation=True)
        self._record_account_actions(
            request,
            users,
            action=ModerationAction.ACTION_ACCOUNT_BANNED,
            note="Permanent staff ban.",
        )
        self.message_user(
            request,
            f"Banned {len(users)} account(s).",
        )

    @admin.action(
        description="Restore access for selected accounts",
        permissions=["change"],
    )
    def restore_account_access(self, request, queryset):
        users = [
            user
            for user in self._eligible_accounts(request, queryset)
            if user.moderation_status
            != self.model.MODERATION_CLEAR
        ]
        now = timezone.now()
        self.model.objects.filter(
            id__in=[user.id for user in users]
        ).update(
            moderation_status=self.model.MODERATION_CLEAR,
            moderation_reason="",
            moderation_expires_at=None,
            moderation_updated_at=now,
            moderation_updated_by=request.user,
        )
        self._record_account_actions(
            request,
            users,
            action=ModerationAction.ACTION_ACCOUNT_RESTORED,
            note=(
                "Account access restored; profile visibility "
                "requires a separate review."
            ),
        )
        self.message_user(
            request,
            (
                f"Restored access for {len(users)} account(s). "
                "Profile visibility was left unchanged."
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
