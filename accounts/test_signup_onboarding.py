from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.forms import CustomSignupForm
from profiles.identity import identity_repair_issues
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


class SafeSignupTests(TestCase):
    def valid_form_data(self):
        return {
            "full_name": "New Heartly User",
            "phone_number": "+256700000000",
            "gender": "female",
            "interested_in": "male",
            "date_of_birth": years_ago(24),
        }

    def test_legacy_friends_preference_is_rejected(self):
        data = self.valid_form_data()
        data["interested_in"] = "friends"

        form = CustomSignupForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("interested_in", form.errors)

    def test_underage_signup_is_rejected(self):
        data = self.valid_form_data()
        data["date_of_birth"] = years_ago(17)

        form = CustomSignupForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("date_of_birth", form.errors)

    def test_implausible_age_is_rejected(self):
        data = self.valid_form_data()
        data["date_of_birth"] = years_ago(101)

        form = CustomSignupForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("date_of_birth", form.errors)

    def test_signup_creates_complete_synchronized_identity(self):
        form = CustomSignupForm(
            data=self.valid_form_data()
        )
        self.assertTrue(form.is_valid(), form.errors)

        user = User.objects.create_user(
            username="new-safe-user",
            email="new-safe-user@example.com",
            password="StrongPass123!",
        )

        form.signup(None, user)

        user.refresh_from_db()
        profile = Profile.objects.get(user=user)

        self.assertEqual(
            identity_repair_issues(user, profile),
            [],
        )
        self.assertEqual(user.gender, "female")
        self.assertEqual(user.interested_in, "male")
        self.assertEqual(profile.gender, "woman")
        self.assertEqual(
            profile.interested_in,
            "men",
        )
        self.assertEqual(profile.age, user.age)


class FirstLoginOnboardingTests(TestCase):
    def test_incomplete_user_is_sent_to_identity_repair(self):
        user = User.objects.create_user(
            username="legacy-incomplete",
            email="legacy-incomplete@example.com",
            password="StrongPass123!",
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("post_login_redirect")
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.url.startswith(
                reverse("profiles:repair_identity")
            )
        )
        self.assertIn("next=", response.url)

    def test_complete_user_is_sent_to_discover(self):
        user = User.objects.create_user(
            username="complete-user",
            email="complete-user@example.com",
            password="StrongPass123!",
            full_name="Complete User",
            gender="male",
            interested_in="female",
            date_of_birth=years_ago(27),
        )
        profile = Profile.objects.get(user=user)
        profile.display_name = "Complete User"
        profile.age = user.age
        profile.gender = "man"
        profile.interested_in = "women"
        profile.save()

        self.client.force_login(user)

        response = self.client.get(
            reverse("post_login_redirect")
        )

        self.assertRedirects(
            response,
            reverse("matches:discover"),
            fetch_redirect_response=False,
        )

    def test_staff_user_is_not_forced_into_dating_onboarding(self):
        user = User.objects.create_user(
            username="staff-user",
            email="staff-user@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("post_login_redirect")
        )

        self.assertRedirects(
            response,
            reverse("feed:feed_home"),
            fetch_redirect_response=False,
        )

    def test_authenticated_welcome_uses_onboarding_router(self):
        user = User.objects.create_user(
            username="welcome-user",
            email="welcome-user@example.com",
            password="StrongPass123!",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("welcome"))

        self.assertRedirects(
            response,
            reverse("post_login_redirect"),
            fetch_redirect_response=False,
        )
