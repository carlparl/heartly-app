from datetime import date

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from ai_features.models import HeartlyMessage
from profiles.models import Profile


User = get_user_model()


def years_ago(years):
    today = date.today()
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(
            year=today.year - years,
            month=2,
            day=28,
        )


@override_settings(
    HEARTLY_ENFORCE_ADULT_IDENTITY=True,
    HEARTLY_REQUIRE_VERIFIED_EMAIL=True,
)
class VerifiedEmailAccessGateTests(TestCase):
    def create_user(
        self,
        username,
        *,
        verified,
        profile_flag=None,
        email=True,
        is_staff=False,
    ):
        current_email = f"{username}@example.com" if email else ""
        user = User.objects.create_user(
            username=username,
            email=current_email,
            password="StrongPass123!",
            full_name=f"{username.title()} User",
            gender="female",
            interested_in="male",
            date_of_birth=years_ago(25),
            is_staff=is_staff,
        )
        profile = Profile.objects.get(user=user)
        profile.display_name = user.full_name
        profile.age = user.age
        profile.gender = Profile.GENDER_WOMAN
        profile.connection_goal = Profile.CONNECTION_DATING
        profile.interested_in = Profile.INTERESTED_IN_MEN
        profile.email_verified = (
            verified if profile_flag is None else profile_flag
        )
        profile.save()

        if current_email:
            EmailAddress.objects.update_or_create(
                user=user,
                email=current_email,
                defaults={
                    "primary": True,
                    "verified": verified,
                },
            )

        return user, profile

    def test_unverified_social_get_redirects_to_account_settings(self):
        user, _profile = self.create_user(
            "unverifiedget",
            verified=False,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("ai_features:ai_coach"))

        self.assertRedirects(
            response,
            reverse("settings_account"),
            fetch_redirect_response=False,
        )
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_unverified_social_post_is_blocked_without_writing(self):
        user, _profile = self.create_user(
            "unverifiedpost",
            verified=False,
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("ai_features:ai_coach_send"),
            {"message": "This request must be blocked."},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["ok"], False)
        self.assertEqual(
            response.json()["verification_url"],
            reverse("settings_account"),
        )
        self.assertFalse(HeartlyMessage.objects.filter(user=user).exists())

    def test_verified_email_allows_stale_false_profile_flag(self):
        user, _profile = self.create_user(
            "verifiedauthority",
            verified=True,
            profile_flag=False,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("ai_features:ai_coach"))

        self.assertEqual(response.status_code, 200)

    def test_unverified_email_blocks_stale_true_profile_flag(self):
        user, _profile = self.create_user(
            "unverifiedauthority",
            verified=False,
            profile_flag=True,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("ai_features:ai_coach"))

        self.assertRedirects(
            response,
            reverse("settings_account"),
            fetch_redirect_response=False,
        )

    def test_missing_current_email_is_not_treated_as_verified(self):
        user, _profile = self.create_user(
            "missingcurrentemail",
            verified=False,
            profile_flag=True,
            email=False,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("ai_features:ai_coach"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("settings_account"))

    def test_staff_bypasses_verified_email_gate(self):
        user, _profile = self.create_user(
            "emailgatestaff",
            verified=False,
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("ai_features:ai_coach"))

        self.assertEqual(response.status_code, 200)
