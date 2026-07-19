from datetime import date

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from matches.models import MatchAction
from profiles.models import Profile


User = get_user_model()


def set_current_email_verified(user, verified):
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={
            "primary": True,
            "verified": verified,
        },
    )


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


def complete_user(
    username,
    *,
    gender,
    interested_in,
    profile_gender,
    profile_preference,
    verified,
):
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="StrongPass123!",
        full_name=username.replace("_", " ").title(),
        gender=gender,
        interested_in=interested_in,
        date_of_birth=years_ago(25),
    )
    profile = Profile.objects.get(user=user)
    profile.display_name = user.full_name
    profile.age = user.age
    profile.gender = profile_gender
    profile.interested_in = profile_preference
    profile.email_verified = verified
    profile.save()
    set_current_email_verified(user, verified)
    return user, profile


@override_settings(
    HEARTLY_REQUIRE_VERIFIED_EMAIL=True
)
class VerifiedEmailDiscoverGateTests(TestCase):
    def setUp(self):
        self.viewer, self.viewer_profile = complete_user(
            "viewer_man",
            gender="male",
            interested_in="female",
            profile_gender=Profile.GENDER_MAN,
            profile_preference=(
                Profile.INTERESTED_IN_WOMEN
            ),
            verified=False,
        )
        self.target, self.target_profile = complete_user(
            "target_woman",
            gender="female",
            interested_in="male",
            profile_gender=Profile.GENDER_WOMAN,
            profile_preference=(
                Profile.INTERESTED_IN_MEN
            ),
            verified=True,
        )
        self.client.force_login(self.viewer)

    def test_unverified_viewer_sees_verification_gate(self):
        response = self.client.get(
            reverse("matches:discover")
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "matches/discover_email_required.html",
        )
        self.assertContains(response, "Verify your email")

    def test_unverified_viewer_cannot_swipe_directly(self):
        response = self.client.post(
            reverse(
                "matches:swipe",
                kwargs={
                    "user_id": self.target.id,
                    "action": MatchAction.LIKE,
                },
            ),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            MatchAction.objects.filter(
                from_user=self.viewer,
                to_user=self.target,
            ).exists()
        )

    def test_unverified_target_is_not_discoverable(self):
        set_current_email_verified(self.viewer, True)
        set_current_email_verified(self.target, False)

        # Deliberately leave the denormalized profile flags stale to prove
        # Discover uses the authoritative current EmailAddress records.
        self.viewer_profile.email_verified = False
        self.viewer_profile.save(
            update_fields=["email_verified", "updated_at"]
        )
        self.target_profile.email_verified = True
        self.target_profile.save(
            update_fields=["email_verified", "updated_at"]
        )

        response = self.client.get(
            reverse("matches:discover")
        )

        self.assertEqual(response.status_code, 200)
        returned_ids = {
            profile.user_id
            for profile in response.context["profiles"]
        }
        self.assertNotIn(self.target.id, returned_ids)


@override_settings(
    HEARTLY_REQUIRE_VERIFIED_EMAIL=False
)
class VerificationRolloutDisabledTests(TestCase):
    def test_unverified_complete_user_is_not_blocked(self):
        viewer, _profile = complete_user(
            "rollout_viewer",
            gender="male",
            interested_in="female",
            profile_gender=Profile.GENDER_MAN,
            profile_preference=(
                Profile.INTERESTED_IN_WOMEN
            ),
            verified=False,
        )
        self.client.force_login(viewer)

        response = self.client.get(
            reverse("matches:discover")
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "matches/discover.html",
        )
