from datetime import date
from urllib.parse import urlencode

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


@override_settings(HEARTLY_ENFORCE_ADULT_IDENTITY=True)
class AdultAccessGateTests(TestCase):
    def create_user(self, username, *, age=25, is_staff=False):
        date_of_birth = years_ago(age) if age is not None else None
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="test-password-123",
            full_name=f"{username.title()} User",
            date_of_birth=date_of_birth,
            gender="female",
            interested_in="male",
            is_staff=is_staff,
        )
        profile, _created = Profile.objects.get_or_create(user=user)
        profile.display_name = f"{username.title()} User"
        profile.age = user.age
        profile.gender = Profile.GENDER_WOMAN
        profile.connection_goal = Profile.CONNECTION_DATING
        profile.interested_in = Profile.INTERESTED_IN_MEN
        profile.save()
        return user, profile

    def expected_repair_url(self, route_name):
        target_url = reverse(route_name)
        query = urlencode({"next": target_url})
        return f"{reverse('profiles:repair_identity')}?{query}"

    def test_anonymous_public_profile_is_not_exposed(self):
        target, _profile = self.create_user("publictarget")

        response = self.client.get(
            reverse("profiles:public_profile", args=[target.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("account_login"), response.url)

    def test_missing_date_of_birth_redirects_social_get_to_repair(self):
        user, _profile = self.create_user("missingdob", age=None)
        self.client.force_login(user)

        response = self.client.get(reverse("feed:feed_home"))

        self.assertRedirects(
            response,
            self.expected_repair_url("feed:feed_home"),
            fetch_redirect_response=False,
        )
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_ineligible_age_redirects_social_get_to_repair(self):
        user, _profile = self.create_user("ineligible", age=17)
        self.client.force_login(user)

        response = self.client.get(reverse("ai_features:ai_coach"))

        self.assertRedirects(
            response,
            self.expected_repair_url("ai_features:ai_coach"),
            fetch_redirect_response=False,
        )

    def test_incomplete_identity_cannot_mutate_social_data(self):
        user, _profile = self.create_user("blockedpost", age=None)
        self.client.force_login(user)

        response = self.client.post(
            reverse("ai_features:ai_coach_send"),
            {"message": "This request must be blocked."},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["ok"], False)
        self.assertEqual(
            response.json()["repair_url"],
            reverse("profiles:repair_identity"),
        )
        self.assertFalse(HeartlyMessage.objects.filter(user=user).exists())

    def test_complete_adult_can_reach_social_surface(self):
        user, _profile = self.create_user("confirmedadult")
        self.client.force_login(user)

        response = self.client.get(reverse("ai_features:ai_coach"))

        self.assertEqual(response.status_code, 200)

    def test_staff_bypasses_identity_gate(self):
        user, _profile = self.create_user(
            "staffuser",
            age=None,
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("ai_features:ai_coach"))

        self.assertEqual(response.status_code, 200)

    def test_identity_repair_remains_available(self):
        user, _profile = self.create_user("repairuser", age=None)
        self.client.force_login(user)

        response = self.client.get(reverse("profiles:repair_identity"))

        self.assertEqual(response.status_code, 200)

    def test_account_settings_remain_available(self):
        user, _profile = self.create_user("settingsuser", age=None)
        self.client.force_login(user)

        response = self.client.get(reverse("settings"))

        self.assertEqual(response.status_code, 200)

    def test_discover_keeps_its_existing_identity_required_page(self):
        user, _profile = self.create_user("discoveruser", age=None)
        self.client.force_login(user)

        response = self.client.get(reverse("matches:discover"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "matches/discover_identity_required.html",
        )
