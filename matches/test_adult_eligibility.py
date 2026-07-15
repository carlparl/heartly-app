from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from profiles.models import Profile


User = get_user_model()


@override_settings(
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher"
    ]
)
class DiscoverAdultEligibilityTests(TestCase):
    def create_profile_user(
        self,
        username,
        *,
        gender,
        interested_in,
        date_of_birth,
        profile_age=None,
    ):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="StrongPass123!",
            gender=(
                "female"
                if gender == Profile.GENDER_WOMAN
                else "male"
            ),
            interested_in=(
                "male"
                if interested_in == Profile.INTERESTED_IN_MEN
                else "female"
            ),
            date_of_birth=date_of_birth,
        )
        profile = Profile.objects.get(user=user)
        profile.display_name = username.replace("_", " ").title()
        profile.gender = gender
        profile.interested_in = interested_in
        profile.age = (
            user.age
            if profile_age is None
            else profile_age
        )
        profile.profile_visible = True
        profile.hidden_by_moderation = False
        profile.save()
        return user, profile

    def setUp(self):
        self.viewer, self.viewer_profile = self.create_profile_user(
            "adult_viewer",
            gender=Profile.GENDER_WOMAN,
            interested_in=Profile.INTERESTED_IN_MEN,
            date_of_birth=date(2000, 1, 1),
            profile_age=None,
        )
        self.client.force_login(self.viewer)

    def returned_user_ids(self):
        response = self.client.get(reverse("matches:discover"))
        return response, {
            profile.user_id
            for profile in response.context["profiles"]
        }

    def test_viewer_without_date_of_birth_cannot_discover(self):
        self.viewer.date_of_birth = None
        self.viewer.save(update_fields=["date_of_birth"])

        self.create_profile_user(
            "adult_candidate",
            gender=Profile.GENDER_MAN,
            interested_in=Profile.INTERESTED_IN_WOMEN,
            date_of_birth=date(1998, 1, 1),
            profile_age=28,
        )

        response, returned_ids = self.returned_user_ids()

        self.assertEqual(returned_ids, set())
        self.assertFalse(
            response.context["viewer_profile_complete"]
        )

    def test_underage_target_is_excluded_even_with_adult_profile_age(self):
        underage, _ = self.create_profile_user(
            "underage_candidate",
            gender=Profile.GENDER_MAN,
            interested_in=Profile.INTERESTED_IN_WOMEN,
            date_of_birth=date.today().replace(
                year=date.today().year - 17
            ),
            profile_age=28,
        )

        _response, returned_ids = self.returned_user_ids()

        self.assertNotIn(underage.id, returned_ids)

    def test_confirmed_adult_target_is_available(self):
        adult, _ = self.create_profile_user(
            "confirmed_adult",
            gender=Profile.GENDER_MAN,
            interested_in=Profile.INTERESTED_IN_WOMEN,
            date_of_birth=date(1998, 1, 1),
            profile_age=None,
        )

        _response, returned_ids = self.returned_user_ids()

        self.assertIn(adult.id, returned_ids)
