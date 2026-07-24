from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from profiles.models import Interest, Profile


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
        self.profile.connection_goal = Profile.CONNECTION_DATING
        self.profile.interested_in = "men"
        self.profile.save()

        self.client.force_login(self.user)

    def profile_version(self):
        self.profile.refresh_from_db()
        return self.profile.updated_at.isoformat(timespec="microseconds")

    def valid_profile_data(self, **overrides):
        data = {
            "profile_version": self.profile_version(),
            "display_name": "Updated Profile User",
            "username": "updatedprofileuser",
            "bio": "Testing reliable profile updates.",
            "gender": "man",
            "connection_goal": "both",
            "interested_in": "women",
        }
        data.update(overrides)
        return data

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
        self.assertNotIn("â", html)
        self.assertNotIn("ðŸ", html)

    def test_authenticated_shell_uses_shared_foundation_and_labeled_navigation(self):
        response = self.client.get(
            reverse("profiles:profile_home")
        )

        self.assertContains(
            response,
            "css/heartly-foundation.css",
        )

        html = response.content.decode("utf-8")
        for label in (
            "Feed",
            "Matches",
            "AI Coach",
            "Chat",
            "Profile",
        ):
            self.assertIn(
                f'<span class="heartly-nav-label">{label}</span>',
                html,
            )

    def test_profile_update_persists_and_synchronizes_identity(self):
        response = self.client.post(
            reverse("profiles:edit_profile"),
            self.valid_profile_data(),
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
        self.assertEqual(
            self.profile.connection_goal,
            Profile.CONNECTION_BOTH,
        )
        self.assertEqual(self.profile.interested_in, "women")
        self.assertEqual(self.profile.age, self.user.age)

        self.assertEqual(self.user.username, "updatedprofileuser")
        self.assertEqual(self.user.full_name, "Updated Profile User")
        self.assertEqual(self.user.first_name, "Updated")
        self.assertEqual(self.user.last_name, "Profile User")
        self.assertEqual(self.user.gender, "male")
        self.assertEqual(self.user.interested_in, "female")

    def test_stale_profile_edit_does_not_overwrite_newer_data(self):
        stale_version = self.profile_version()
        self.profile.bio = "Saved by another request."
        self.profile.save(update_fields=["bio", "updated_at"])

        response = self.client.post(
            reverse("profiles:edit_profile"),
            self.valid_profile_data(
                profile_version=stale_version,
                bio="Stale browser value.",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "updated in another request")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.bio, "Saved by another request.")

    def test_profile_edit_pages_are_not_cached(self):
        for route_name in (
            "profiles:edit_profile",
            "profiles:edit_interests",
        ):
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 200)
            cache_control = response.headers.get("Cache-Control", "")
            self.assertIn("no-store", cache_control)
            self.assertIn("max-age=0", cache_control)

    def test_interest_update_is_versioned_and_transactional(self):
        interest = Interest.objects.create(name="Reliability testing")
        response = self.client.get(reverse("profiles:edit_interests"))
        version = response.context["form"]["profile_version"].value()
        previous_updated_at = self.profile.updated_at

        response = self.client.post(
            reverse("profiles:edit_interests"),
            {
                "profile_version": version,
                "interests": [str(interest.id)],
            },
        )

        self.assertRedirects(
            response,
            reverse("profiles:profile_home"),
            fetch_redirect_response=False,
        )
        self.profile.refresh_from_db()
        self.assertEqual(
            list(self.profile.interests.values_list("id", flat=True)),
            [interest.id],
        )
        self.assertGreater(self.profile.updated_at, previous_updated_at)

    def test_stale_interest_edit_is_rejected(self):
        interest = Interest.objects.create(name="Stale interest")
        response = self.client.get(reverse("profiles:edit_interests"))
        stale_version = response.context["form"]["profile_version"].value()
        self.profile.bio = "Concurrent profile change."
        self.profile.save(update_fields=["bio", "updated_at"])

        response = self.client.post(
            reverse("profiles:edit_interests"),
            {
                "profile_version": stale_version,
                "interests": [str(interest.id)],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "updated in another request")
        self.assertFalse(self.profile.interests.filter(id=interest.id).exists())

    def test_repair_form_preserves_goal_without_guessing_preference(self):
        self.user.interested_in = "friends"
        self.user.save(update_fields=["interested_in"])

        self.profile.connection_goal = (
            Profile.CONNECTION_FRIENDSHIP
        )
        self.profile.interested_in = "friends"
        self.profile.save(
            update_fields=[
                "connection_goal",
                "interested_in",
                "updated_at",
            ]
        )

        response = self.client.get(
            reverse("profiles:repair_identity")
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(
            form.initial["connection_goal"],
            Profile.CONNECTION_FRIENDSHIP,
        )
        self.assertEqual(form.initial["interested_in"], "")

    def test_identity_repair_synchronizes_friendship_goal(self):
        self.user.interested_in = "friends"
        self.user.save(update_fields=["interested_in"])

        self.profile.connection_goal = (
            Profile.CONNECTION_FRIENDSHIP
        )
        self.profile.interested_in = "friends"
        self.profile.save(
            update_fields=[
                "connection_goal",
                "interested_in",
                "updated_at",
            ]
        )

        response = self.client.post(
            reverse("profiles:repair_identity"),
            {
                "display_name": "Friendship User",
                "date_of_birth": "2000-01-01",
                "gender": "woman",
                "connection_goal": "friendship",
                "interested_in": "everyone",
                "next": reverse("matches:discover"),
            },
        )

        self.assertRedirects(
            response,
            reverse("matches:discover"),
            fetch_redirect_response=False,
        )

        self.user.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertEqual(
            self.profile.connection_goal,
            Profile.CONNECTION_FRIENDSHIP,
        )
        self.assertEqual(
            self.profile.interested_in,
            Profile.INTERESTED_IN_EVERYONE,
        )
        self.assertEqual(self.user.interested_in, "both")
