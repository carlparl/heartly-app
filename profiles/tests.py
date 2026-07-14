from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from profiles.models import Profile


User = get_user_model()


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)
class ProfilesRoutesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="profileuser",
            email="profileuser@example.com",
            password="StrongPass123!",
            full_name="Original Profile User",
            gender="female",
            interested_in="male",
            date_of_birth=date(2000, 1, 1),
        )

        self.profile = Profile.objects.get(user=self.user)
        self.profile.display_name = "Original Profile User"
        self.profile.age = self.user.age
        self.profile.gender = "woman"
        self.profile.interested_in = "men"
        self.profile.save()

        self.client.force_login(self.user)

    def test_profile_home_loads(self):
        response = self.client.get(
            reverse("profiles:profile_home")
        )
        self.assertEqual(response.status_code, 200)

    def test_edit_profile_loads_with_one_submit_button(self):
        response = self.client.get(
            reverse("profiles:edit_profile")
        )

        self.assertEqual(response.status_code, 200)

        html = response.content.decode("utf-8")
        self.assertEqual(html.count('<button type="submit"'), 1)

    def test_profile_update_persists_and_synchronizes_identity(self):
        response = self.client.post(
            reverse("profiles:edit_profile"),
            {
                "display_name": "Updated Profile User",
                "username": "updatedprofileuser",
                "bio": "Testing reliable profile updates.",
                "gender": "man",
                "interested_in": "women",
            },
        )

        self.assertRedirects(
            response,
            reverse("profiles:profile_home"),
            fetch_redirect_response=False,
        )

        self.user.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertEqual(
            self.profile.display_name,
            "Updated Profile User",
        )
        self.assertEqual(
            self.profile.bio,
            "Testing reliable profile updates.",
        )
        self.assertEqual(self.profile.gender, "man")
        self.assertEqual(self.profile.interested_in, "women")
        self.assertEqual(self.profile.age, self.user.age)

        self.assertEqual(self.user.username, "updatedprofileuser")
        self.assertEqual(self.user.full_name, "Updated Profile User")
        self.assertEqual(self.user.first_name, "Updated")
        self.assertEqual(self.user.last_name, "Profile User")
        self.assertEqual(self.user.gender, "male")
        self.assertEqual(self.user.interested_in, "female")
