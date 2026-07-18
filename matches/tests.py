from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from profiles.models import Profile, UserBlock

from .models import MatchAction, MutualMatch


User = get_user_model()


PROFILE_GENDER_TO_USER_GENDER = {
    Profile.GENDER_MAN: "male",
    Profile.GENDER_WOMAN: "female",
    Profile.GENDER_NON_BINARY: "non_binary",
    Profile.GENDER_OTHER: "prefer_not_to_say",
}

PROFILE_PREFERENCE_TO_USER_PREFERENCE = {
    Profile.INTERESTED_IN_MEN: "male",
    Profile.INTERESTED_IN_WOMEN: "female",
    Profile.INTERESTED_IN_EVERYONE: "both",
}


def date_of_birth_for_age(age):
    today = date.today()

    try:
        return today.replace(year=today.year - age)
    except ValueError:
        return today.replace(
            year=today.year - age,
            month=2,
            day=28,
        )


@override_settings(
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher"
    ]
)
class MatchTestBase(TestCase):
    def create_profile_user(
        self,
        username,
        *,
        gender,
        interested_in,
        age=28,
        display_name=None,
        visible=True,
        moderated=False,
        active=True,
        staff=False,
    ):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="StrongPass123!",
            date_of_birth=date_of_birth_for_age(age),
            gender=PROFILE_GENDER_TO_USER_GENDER[gender],
            interested_in=(
                PROFILE_PREFERENCE_TO_USER_PREFERENCE[
                    interested_in
                ]
            ),
            is_active=active,
            is_staff=staff,
        )

        profile = Profile.objects.get(user=user)
        profile.display_name = (
            display_name
            if display_name is not None
            else username.replace("_", " ").title()
        )
        profile.age = age
        profile.gender = gender
        profile.interested_in = interested_in
        profile.profile_visible = visible
        profile.hidden_by_moderation = moderated
        profile.save()

        return user, profile


class DiscoverTests(MatchTestBase):
    def setUp(self):
        self.viewer, self.viewer_profile = (
            self.create_profile_user(
                "viewer_woman",
                gender=Profile.GENDER_WOMAN,
                interested_in=(
                    Profile.INTERESTED_IN_MEN
                ),
            )
        )
        self.client.force_login(self.viewer)

    def test_discover_returns_only_safe_mutual_candidates(self):
        compatible, _ = self.create_profile_user(
            "compatible_man",
            gender=Profile.GENDER_MAN,
            interested_in=(
                Profile.INTERESTED_IN_WOMEN
            ),
        )

        wrong_gender, _ = self.create_profile_user(
            "wrong_gender",
            gender=Profile.GENDER_WOMAN,
            interested_in=(
                Profile.INTERESTED_IN_WOMEN
            ),
        )

        rejects_viewer, _ = self.create_profile_user(
            "rejects_viewer",
            gender=Profile.GENDER_MAN,
            interested_in=Profile.INTERESTED_IN_MEN,
        )

        underage, _ = self.create_profile_user(
            "underage",
            gender=Profile.GENDER_MAN,
            interested_in=(
                Profile.INTERESTED_IN_WOMEN
            ),
            age=17,
        )

        incomplete, _ = self.create_profile_user(
            "incomplete",
            gender=Profile.GENDER_MAN,
            interested_in=(
                Profile.INTERESTED_IN_WOMEN
            ),
            display_name="",
        )

        private, _ = self.create_profile_user(
            "private_profile",
            gender=Profile.GENDER_MAN,
            interested_in=(
                Profile.INTERESTED_IN_WOMEN
            ),
            visible=False,
        )

        moderated, _ = self.create_profile_user(
            "moderated_profile",
            gender=Profile.GENDER_MAN,
            interested_in=(
                Profile.INTERESTED_IN_WOMEN
            ),
            moderated=True,
        )

        inactive, _ = self.create_profile_user(
            "inactive_profile",
            gender=Profile.GENDER_MAN,
            interested_in=(
                Profile.INTERESTED_IN_WOMEN
            ),
            active=False,
        )

        staff, _ = self.create_profile_user(
            "staff_profile",
            gender=Profile.GENDER_MAN,
            interested_in=(
                Profile.INTERESTED_IN_WOMEN
            ),
            staff=True,
        )

        blocked, _ = self.create_profile_user(
            "blocked_profile",
            gender=Profile.GENDER_MAN,
            interested_in=(
                Profile.INTERESTED_IN_WOMEN
            ),
        )
        UserBlock.objects.create(
            blocker=self.viewer,
            blocked=blocked,
        )

        acted, _ = self.create_profile_user(
            "already_acted",
            gender=Profile.GENDER_MAN,
            interested_in=(
                Profile.INTERESTED_IN_WOMEN
            ),
        )
        MatchAction.objects.create(
            from_user=self.viewer,
            to_user=acted,
            action=MatchAction.PASS,
        )

        response = self.client.get(
            reverse("matches:discover")
        )

        self.assertEqual(response.status_code, 200)

        returned_ids = {
            profile.user_id
            for profile in response.context["profiles"]
        }

        self.assertEqual(returned_ids, {compatible.id})

        excluded_users = {
            wrong_gender.id,
            rejects_viewer.id,
            underage.id,
            incomplete.id,
            private.id,
            moderated.id,
            inactive.id,
            staff.id,
            blocked.id,
            acted.id,
            self.viewer.id,
        }
        self.assertTrue(
            returned_ids.isdisjoint(excluded_users)
        )

    def test_incomplete_viewer_receives_no_candidates(self):
        self.viewer_profile.display_name = ""
        self.viewer_profile.save(
            update_fields=[
                "display_name",
                "updated_at",
            ]
        )

        self.create_profile_user(
            "otherwise_compatible",
            gender=Profile.GENDER_MAN,
            interested_in=(
                Profile.INTERESTED_IN_WOMEN
            ),
        )

        response = self.client.get(
            reverse("matches:discover")
        )

        self.assertEqual(
            list(response.context["profiles"]),
            [],
        )
        self.assertFalse(
            response.context[
                "viewer_profile_complete"
            ]
        )

    def test_search_does_not_bypass_compatibility(self):
        compatible, _ = self.create_profile_user(
            "alex_compatible",
            gender=Profile.GENDER_MAN,
            interested_in=(
                Profile.INTERESTED_IN_WOMEN
            ),
            display_name="Alex Compatible",
        )
        self.create_profile_user(
            "alex_incompatible",
            gender=Profile.GENDER_WOMAN,
            interested_in=(
                Profile.INTERESTED_IN_WOMEN
            ),
            display_name="Alex Incompatible",
        )

        response = self.client.get(
            reverse("matches:discover"),
            {"q": "Alex"},
        )

        returned_ids = {
            profile.user_id
            for profile in response.context["profiles"]
        }

        self.assertEqual(returned_ids, {compatible.id})


class SwipeTests(MatchTestBase):
    def setUp(self):
        self.viewer, _ = self.create_profile_user(
            "swipe_viewer",
            gender=Profile.GENDER_WOMAN,
            interested_in=Profile.INTERESTED_IN_MEN,
        )
        self.target, _ = self.create_profile_user(
            "swipe_target",
            gender=Profile.GENDER_MAN,
            interested_in=(
                Profile.INTERESTED_IN_WOMEN
            ),
        )
        self.client.force_login(self.viewer)

    def ajax_post(self, action, user=None):
        target = user or self.target

        return self.client.post(
            reverse(
                "matches:swipe",
                kwargs={
                    "user_id": target.id,
                    "action": action,
                },
            ),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_pass_records_action_without_match(self):
        response = self.ajax_post(MatchAction.PASS)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "ok": True,
                "matched": False,
            },
        )
        self.assertTrue(
            MatchAction.objects.filter(
                from_user=self.viewer,
                to_user=self.target,
                action=MatchAction.PASS,
            ).exists()
        )
        self.assertFalse(
            MutualMatch.objects.exists()
        )

    @patch("matches.views.notify_profile_like")
    @patch("matches.views.notify_mutual_match")
    def test_reciprocal_like_creates_one_match_and_notifies_once(
        self,
        notify_mutual_match,
        notify_profile_like,
    ):
        MatchAction.objects.create(
            from_user=self.target,
            to_user=self.viewer,
            action=MatchAction.LIKE,
        )

        first_response = self.ajax_post(
            MatchAction.LIKE
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertTrue(
            first_response.json()["matched"]
        )
        self.assertEqual(
            MutualMatch.objects.count(),
            1,
        )
        notify_mutual_match.assert_called_once_with(
            MutualMatch.objects.get(),
            self.viewer,
            self.target,
        )
        notify_profile_like.assert_called_once_with(
            self.viewer,
            self.target,
            active=False,
        )

        notify_mutual_match.reset_mock()
        notify_profile_like.reset_mock()

        second_response = self.ajax_post(
            MatchAction.LIKE
        )

        self.assertEqual(second_response.status_code, 200)
        self.assertTrue(
            second_response.json()["matched"]
        )
        self.assertEqual(
            MutualMatch.objects.count(),
            1,
        )
        notify_mutual_match.assert_not_called()
        notify_profile_like.assert_called_once_with(
            self.viewer,
            self.target,
            active=False,
        )

    def test_direct_swipe_cannot_bypass_compatibility(self):
        incompatible, _ = self.create_profile_user(
            "incompatible_target",
            gender=Profile.GENDER_WOMAN,
            interested_in=(
                Profile.INTERESTED_IN_WOMEN
            ),
        )

        response = self.ajax_post(
            MatchAction.LIKE,
            incompatible,
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            MatchAction.objects.filter(
                from_user=self.viewer,
                to_user=incompatible,
            ).exists()
        )

    def test_blocked_profile_cannot_be_swiped(self):
        UserBlock.objects.create(
            blocker=self.target,
            blocked=self.viewer,
        )

        response = self.ajax_post(
            MatchAction.LIKE
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            MatchAction.objects.filter(
                from_user=self.viewer,
                to_user=self.target,
            ).exists()
        )

    def test_swipe_requires_post(self):
        response = self.client.get(
            reverse(
                "matches:swipe",
                kwargs={
                    "user_id": self.target.id,
                    "action": MatchAction.LIKE,
                },
            )
        )

        self.assertEqual(response.status_code, 405)


class MutualMatchModelTests(MatchTestBase):
    def test_create_safe_is_canonical_and_idempotent(self):
        user_a, _ = self.create_profile_user(
            "canonical_a",
            gender=Profile.GENDER_WOMAN,
            interested_in=Profile.INTERESTED_IN_MEN,
        )
        user_b, _ = self.create_profile_user(
            "canonical_b",
            gender=Profile.GENDER_MAN,
            interested_in=(
                Profile.INTERESTED_IN_WOMEN
            ),
        )

        first_match, first_created = (
            MutualMatch.create_safe(
                user_a,
                user_b,
                return_created=True,
            )
        )
        second_match, second_created = (
            MutualMatch.create_safe(
                user_b,
                user_a,
                return_created=True,
            )
        )

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(
            first_match.pk,
            second_match.pk,
        )
        self.assertEqual(
            MutualMatch.objects.count(),
            1,
        )
        self.assertLess(
            first_match.user_one_id,
            first_match.user_two_id,
        )

    def test_create_safe_rejects_self_match(self):
        user, _ = self.create_profile_user(
            "self_match",
            gender=Profile.GENDER_WOMAN,
            interested_in=(
                Profile.INTERESTED_IN_EVERYONE
            ),
        )

        match, created = MutualMatch.create_safe(
            user,
            user,
            return_created=True,
        )

        self.assertIsNone(match)
        self.assertFalse(created)
        self.assertFalse(
            MutualMatch.objects.exists()
        )


class YourMatchesTests(MatchTestBase):
    def test_blocked_existing_match_is_not_displayed(self):
        viewer, _ = self.create_profile_user(
            "matches_viewer",
            gender=Profile.GENDER_WOMAN,
            interested_in=Profile.INTERESTED_IN_MEN,
        )
        other, _ = self.create_profile_user(
            "matches_other",
            gender=Profile.GENDER_MAN,
            interested_in=(
                Profile.INTERESTED_IN_WOMEN
            ),
        )

        MutualMatch.create_safe(viewer, other)
        UserBlock.objects.create(
            blocker=viewer,
            blocked=other,
        )

        self.client.force_login(viewer)

        response = self.client.get(
            reverse("matches:your_matches")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["match_cards"],
            [],
        )
