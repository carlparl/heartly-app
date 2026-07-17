from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from feed.models import Story, StoryView
from feed.views import (
    story_detail,
    story_groups_for,
    story_playlist_for,
)


User = get_user_model()


class StoryPlaylistNavigationTests(TestCase):
    def setUp(self):
        self.viewer = User.objects.create_user(
            username="storyviewer",
            email="storyviewer@example.com",
            password="Pass12345!",
        )
        self.author_a = User.objects.create_user(
            username="storyauthora",
            email="storyauthora@example.com",
            password="Pass12345!",
        )
        self.author_b = User.objects.create_user(
            username="storyauthorb",
            email="storyauthorb@example.com",
            password="Pass12345!",
        )

        self.a_old = Story.objects.create(
            author=self.author_a,
            image="stories/images/a-old.jpg",
            caption="A old",
        )
        self.a_new = Story.objects.create(
            author=self.author_a,
            image="stories/images/a-new.jpg",
            caption="A new",
        )
        self.b_only = Story.objects.create(
            author=self.author_b,
            image="stories/images/b-only.jpg",
            caption="B only",
        )

        self.factory = RequestFactory()

    def render_story(self, story):
        request = self.factory.get(
            reverse(
                "feed:story_detail",
                args=[story.id],
            )
        )
        request.user = self.viewer

        def fake_render(
            request,
            template_name,
            context,
        ):
            response = HttpResponse(status=200)
            response.template_name = template_name
            response.context_data = context
            return response

        with patch(
            "feed.views.render",
            side_effect=fake_render,
        ):
            return story_detail(request, story.id)

    def test_playlist_contains_every_visible_author(self):
        playlist = story_playlist_for(self.viewer)
        playlist_ids = [
            story.id
            for story in playlist
        ]

        self.assertEqual(
            playlist_ids,
            [
                self.b_only.id,
                self.a_old.id,
                self.a_new.id,
            ],
        )

    def test_navigation_crosses_author_boundary(self):
        response = self.render_story(self.a_old)
        context = response.context_data

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            context["previous_story_id"],
            self.b_only.id,
        )
        self.assertEqual(
            context["next_story_id"],
            self.a_new.id,
        )
        self.assertEqual(
            context["story_position"],
            2,
        )
        self.assertEqual(
            context["story_total"],
            3,
        )

    def test_first_story_moves_forward_to_next_author(self):
        response = self.render_story(self.b_only)
        context = response.context_data

        self.assertIsNone(
            context["previous_story_id"]
        )
        self.assertEqual(
            context["next_story_id"],
            self.a_old.id,
        )

    def test_last_story_moves_backward(self):
        response = self.render_story(self.a_new)
        context = response.context_data

        self.assertEqual(
            context["previous_story_id"],
            self.a_old.id,
        )
        self.assertIsNone(
            context["next_story_id"]
        )

    def test_tray_entry_is_oldest_unseen_story(self):
        StoryView.objects.create(
            story=self.a_old,
            viewer=self.viewer,
        )

        groups = story_groups_for(self.viewer)
        group_a = next(
            group
            for group in groups
            if group["author_id"] == self.author_a.id
        )

        self.assertEqual(
            group_a["entry_story"].id,
            self.a_new.id,
        )
        self.assertTrue(group_a["has_unseen"])

    def test_seen_group_restarts_from_oldest_story(self):
        StoryView.objects.create(
            story=self.a_old,
            viewer=self.viewer,
        )
        StoryView.objects.create(
            story=self.a_new,
            viewer=self.viewer,
        )

        groups = story_groups_for(self.viewer)
        group_a = next(
            group
            for group in groups
            if group["author_id"] == self.author_a.id
        )

        self.assertEqual(
            group_a["entry_story"].id,
            self.a_old.id,
        )
        self.assertFalse(group_a["has_unseen"])
