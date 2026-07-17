from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from feed.models import Story, StoryReaction
from feed.views import story_detail
from notifications.models import Notification


User = get_user_model()


class StoryReactionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="storyowner",
            email="storyowner@example.com",
            password="Pass12345!",
        )
        self.viewer = User.objects.create_user(
            username="storyreactor",
            email="storyreactor@example.com",
            password="Pass12345!",
        )
        self.story = Story.objects.create(
            author=self.owner,
            image="stories/images/reaction-test.jpg",
            caption="Reaction test",
        )
        self.client.force_login(self.viewer)

    def react(self, reaction_type):
        return self.client.post(
            reverse(
                "feed:react_story",
                args=[self.story.id],
            ),
            {
                "reaction_type": reaction_type,
                "_ajax": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

    def test_reaction_is_created(self):
        response = self.react("love")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            StoryReaction.objects.count(),
            1,
        )
        reaction = StoryReaction.objects.get()
        self.assertEqual(
            reaction.reaction_type,
            "love",
        )
        self.assertEqual(
            response.json()["reaction_counts"]["love"],
            1,
        )

    def test_duplicate_tap_is_idempotent(self):
        first = self.react("laugh")
        second = self.react("laugh")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            StoryReaction.objects.count(),
            1,
        )
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.owner,
                actor=self.viewer,
                related_object_type=(
                    "feed.story_reaction"
                ),
                related_object_id=self.story.id,
            ).count(),
            1,
        )

    def test_changing_reaction_updates_same_rows(self):
        self.react("love")
        response = self.react("wow")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            StoryReaction.objects.count(),
            1,
        )
        reaction = StoryReaction.objects.get()
        self.assertEqual(
            reaction.reaction_type,
            "wow",
        )

        notifications = Notification.objects.filter(
            recipient=self.owner,
            actor=self.viewer,
            related_object_type=(
                "feed.story_reaction"
            ),
            related_object_id=self.story.id,
        )
        self.assertEqual(
            notifications.count(),
            1,
        )
        self.assertIn(
            "😮",
            notifications.get().title,
        )

    def test_invalid_reaction_is_rejected(self):
        response = self.react("invalid")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            StoryReaction.objects.count(),
            0,
        )

    def test_owner_cannot_react_to_own_story(self):
        self.client.force_login(self.owner)
        response = self.react("love")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            StoryReaction.objects.count(),
            0,
        )

    def test_expired_story_cannot_receive_reaction(self):
        Story.objects.filter(
            id=self.story.id
        ).update(
            expires_at=(
                timezone.now() -
                timedelta(seconds=1)
            )
        )

        response = self.react("love")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            StoryReaction.objects.count(),
            0,
        )

    def test_deleted_story_cannot_receive_reaction(self):
        story_id = self.story.id
        self.story.delete()

        response = self.client.post(
            reverse(
                "feed:react_story",
                args=[story_id],
            ),
            {
                "reaction_type": "love",
                "_ajax": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            StoryReaction.objects.count(),
            0,
        )

    def test_story_owner_context_has_reaction_totals(self):
        StoryReaction.objects.create(
            story=self.story,
            user=self.viewer,
            reaction_type="laugh",
        )

        request = RequestFactory().get(
            reverse(
                "feed:story_detail",
                args=[self.story.id],
            )
        )
        request.user = self.owner

        def fake_render(
            request,
            template_name,
            context,
        ):
            response = HttpResponse(status=200)
            response.context_data = context
            response.template_name = template_name
            return response

        with patch(
            "feed.views.render",
            side_effect=fake_render,
        ):
            response = story_detail(
                request,
                self.story.id,
            )

        story = response.context_data["story"]
        self.assertEqual(
            story.reaction_total,
            1,
        )
        self.assertEqual(
            story.reaction_counts["laugh"],
            1,
        )


class StoryReactionContractTests(TestCase):
    def read_source(self, relative_path):
        return (
            Path(settings.BASE_DIR) /
            relative_path
        ).read_text(encoding="utf-8")

    def test_story_template_has_reaction_controls(self):
        source = self.read_source(
            "templates/feed/story_detail.html"
        )

        self.assertIn(
            "data-story-reaction-form",
            source,
        )
        self.assertIn(
            "data-story-reaction-button",
            source,
        )
        self.assertIn(
            "story.reaction_counts.love",
            source,
        )
        self.assertIn(
            "js/heartly-story-reactions.js",
            source,
        )

    def test_reaction_javascript_has_rollback(self):
        source = self.read_source(
            "static/js/heartly-story-reactions.js"
        )

        self.assertIn(
            "const previous = activeReaction(form)",
            source,
        )
        self.assertIn(
            "setActiveReaction(form, previous)",
            source,
        )
        self.assertIn(
            "heartly:story-interaction-start",
            source,
        )
        self.assertIn(
            "heartly:story-interaction-end",
            source,
        )

    def test_playback_controller_handles_reaction_pause(self):
        source = self.read_source(
            "static/js/heartly-story-viewer.js"
        )

        self.assertIn(
            "pauseForExternalInteraction",
            source,
        )
        self.assertIn(
            "resumeAfterExternalInteraction",
            source,
        )
