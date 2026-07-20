from datetime import timedelta
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from profiles.models import ModerationAction, Profile

from .admin import CustomUserAdmin


User = get_user_model()


@override_settings(
    HEARTLY_ENFORCE_ADULT_IDENTITY=False,
    HEARTLY_REQUIRE_VERIFIED_EMAIL=False,
)
class AccountModerationTests(TestCase):
    def setUp(self):
        self.moderator = User.objects.create_user(
            username="restriction_staff",
            email="restriction-staff@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.user = User.objects.create_user(
            username="restricted_member",
            email="restricted-member@example.com",
            password="StrongPass123!",
        )

    def restrict(self, status, expires_at=None):
        self.user.moderation_status = status
        self.user.moderation_expires_at = expires_at
        self.user.save(
            update_fields=[
                "moderation_status",
                "moderation_expires_at",
            ]
        )

    def test_suspended_and_banned_accounts_are_blocked(self):
        self.client.force_login(self.user)
        self.restrict(
            User.MODERATION_SUSPENDED,
            timezone.now() + timedelta(days=1),
        )
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(
            response,
            "Account unavailable",
            status_code=403,
        )
        self.assertEqual(
            self.client.get(reverse("privacy_policy")).status_code,
            200,
        )

        self.restrict(User.MODERATION_BANNED)
        response = self.client.post(
            reverse("settings"),
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["moderation_status"],
            User.MODERATION_BANNED,
        )

    def test_expired_suspension_and_staff_account_can_access(self):
        self.client.force_login(self.user)
        self.restrict(
            User.MODERATION_SUSPENDED,
            timezone.now() - timedelta(minutes=1),
        )
        self.assertEqual(
            self.client.get(reverse("settings")).status_code,
            200,
        )

        self.moderator.moderation_status = User.MODERATION_BANNED
        self.moderator.save(update_fields=["moderation_status"])
        self.client.force_login(self.moderator)
        self.assertEqual(
            self.client.get(reverse("settings")).status_code,
            200,
        )

    def test_admin_actions_hide_and_audit_without_auto_restore(self):
        request = RequestFactory().post("/admin/accounts/customuser/")
        request.user = self.moderator
        model_admin = CustomUserAdmin(User, admin.site)
        queryset = User.objects.filter(pk=self.user.pk)

        with patch.object(model_admin, "message_user"):
            model_admin.suspend_accounts_for_seven_days(
                request,
                queryset,
            )
        self.user.refresh_from_db()
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(
            self.user.moderation_status,
            User.MODERATION_SUSPENDED,
        )
        self.assertTrue(profile.hidden_by_moderation)
        self.assertTrue(
            ModerationAction.objects.filter(
                target_user=self.user,
                action=(
                    ModerationAction.ACTION_ACCOUNT_SUSPENDED
                ),
            ).exists()
        )

        with patch.object(model_admin, "message_user"):
            model_admin.restore_account_access(request, queryset)
        self.user.refresh_from_db()
        profile.refresh_from_db()
        self.assertEqual(
            self.user.moderation_status,
            User.MODERATION_CLEAR,
        )
        self.assertTrue(profile.hidden_by_moderation)
        self.assertTrue(
            ModerationAction.objects.filter(
                target_user=self.user,
                action=(
                    ModerationAction.ACTION_ACCOUNT_RESTORED
                ),
            ).exists()
        )

    def test_expired_release_is_dry_run_safe_and_idempotent(self):
        self.restrict(
            User.MODERATION_SUSPENDED,
            timezone.now() - timedelta(hours=1),
        )
        call_command("release_expired_suspensions")
        self.user.refresh_from_db()
        self.assertEqual(
            self.user.moderation_status,
            User.MODERATION_SUSPENDED,
        )

        call_command("release_expired_suspensions", apply=True)
        call_command("release_expired_suspensions", apply=True)
        self.user.refresh_from_db()
        self.assertEqual(
            self.user.moderation_status,
            User.MODERATION_CLEAR,
        )
        self.assertEqual(
            ModerationAction.objects.filter(
                target_user=self.user,
                action=(
                    ModerationAction.ACTION_ACCOUNT_RESTORED
                ),
            ).count(),
            1,
        )
