from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from profiles.identity import age_from_date_of_birth
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


class IdentityRepairTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="repair_user",
            email="repair@example.com",
            password="StrongPass123!",
            gender="",
            interested_in="friends",
            date_of_birth=None,
        )
        self.profile = Profile.objects.get(user=self.user)
        self.profile.display_name = ""
        self.profile.age = None
        self.profile.gender = ""
        self.profile.interested_in = ""
        self.profile.save()
        self.client.force_login(self.user)

    def test_repair_page_explains_missing_fields(self):
        response = self.client.get(
            reverse("profiles:repair_identity")
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "profiles/identity_repair.html",
        )
        self.assertContains(
            response,
            "Confirm your date of birth.",
        )
        self.assertContains(
            response,
            "Choose your gender.",
        )

    def test_underage_date_is_rejected_without_changes(self):
        response = self.client.post(
            reverse("profiles:repair_identity"),
            {
                "display_name": "Repair User",
                "date_of_birth": years_ago(17).isoformat(),
                "gender": Profile.GENDER_MAN,
                "interested_in": (
                    Profile.INTERESTED_IN_WOMEN
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "confirmed adults between 18 and 100",
        )

        self.user.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertIsNone(self.user.date_of_birth)
        self.assertIsNone(self.profile.age)
        self.assertEqual(self.profile.gender, "")

    def test_valid_repair_synchronizes_user_and_profile(self):
        date_of_birth = years_ago(25)

        response = self.client.post(
            reverse("profiles:repair_identity"),
            {
                "display_name": "Repair User",
                "date_of_birth": date_of_birth.isoformat(),
                "gender": Profile.GENDER_WOMAN,
                "interested_in": Profile.INTERESTED_IN_MEN,
            },
        )

        self.assertRedirects(
            response,
            reverse("matches:discover"),
            fetch_redirect_response=False,
        )

        self.user.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertEqual(self.user.full_name, "Repair User")
        self.assertEqual(
            self.user.date_of_birth,
            date_of_birth,
        )
        self.assertEqual(self.user.gender, "female")
        self.assertEqual(self.user.interested_in, "male")
        self.assertEqual(
            self.profile.display_name,
            "Repair User",
        )
        self.assertEqual(
            self.profile.age,
            age_from_date_of_birth(date_of_birth),
        )
        self.assertEqual(
            self.profile.gender,
            Profile.GENDER_WOMAN,
        )
        self.assertEqual(
            self.profile.interested_in,
            Profile.INTERESTED_IN_MEN,
        )

    def test_external_next_url_is_not_used(self):
        date_of_birth = years_ago(25)

        response = self.client.post(
            reverse("profiles:repair_identity"),
            {
                "next": "https://example.invalid/steal",
                "display_name": "Repair User",
                "date_of_birth": date_of_birth.isoformat(),
                "gender": Profile.GENDER_MAN,
                "interested_in": (
                    Profile.INTERESTED_IN_WOMEN
                ),
            },
        )

        self.assertRedirects(
            response,
            reverse("matches:discover"),
            fetch_redirect_response=False,
        )
