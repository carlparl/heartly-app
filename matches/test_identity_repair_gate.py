from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from matches.models import MatchAction
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


class IdentityRepairGateTests(TestCase):
    def setUp(self):
        self.viewer = User.objects.create_user(
            username="incomplete_viewer",
            email="incomplete-viewer@example.com",
            password="StrongPass123!",
            gender="",
            interested_in="friends",
            date_of_birth=None,
        )
        self.viewer_profile = Profile.objects.get(
            user=self.viewer
        )
        self.viewer_profile.display_name = ""
        self.viewer_profile.age = None
        self.viewer_profile.gender = ""
        self.viewer_profile.interested_in = ""
        self.viewer_profile.save()

        self.target = User.objects.create_user(
            username="eligible_target",
            email="eligible-target@example.com",
            password="StrongPass123!",
            gender="female",
            interested_in="male",
            date_of_birth=years_ago(24),
        )
        self.target_profile = Profile.objects.get(
            user=self.target
        )
        self.target_profile.display_name = "Eligible Target"
        self.target_profile.age = self.target.age
        self.target_profile.gender = Profile.GENDER_WOMAN
        self.target_profile.interested_in = (
            Profile.INTERESTED_IN_MEN
        )
        self.target_profile.save()

        self.client.force_login(self.viewer)

    def test_discover_shows_identity_repair_screen(self):
        response = self.client.get(
            reverse("matches:discover")
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "matches/discover_identity_required.html",
        )
        self.assertFalse(
            response.context["viewer_profile_complete"]
        )
        self.assertEqual(
            list(response.context["profiles"]),
            [],
        )
        self.assertContains(response, "Confirm details")

    def test_direct_swipe_is_rejected(self):
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
        self.assertIn(
            "Complete your identity details",
            response.json()["error"],
        )
