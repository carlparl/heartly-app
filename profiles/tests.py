from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse


User = get_user_model()


class ProfilesRoutesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="profileuser",
            email="profileuser@example.com",
            password="StrongPass123!"
        )
        self.client.login(username="profileuser", password="StrongPass123!")

    def test_profile_home_loads(self):
        response = self.client.get(reverse("profile_home"))
        self.assertEqual(response.status_code, 200)

    def test_profile_update_works(self):
        response = self.client.post(reverse("profile_home"), {
            "display_name": "Profile User",
            "bio": "Testing profile update.",
        })

        self.assertEqual(response.status_code, 302)

        self.user.refresh_from_db()
        self.assertEqual(self.user.profile.display_name, "Profile User")
        self.assertEqual(self.user.profile.bio, "Testing profile update.")