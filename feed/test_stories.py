from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .models import STORY_LIFETIME, Story, StoryView


class StoryModelTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.author = User.objects.create_user(
            username="story-author",
            email="story-author@example.com",
            password="test-password-123",
        )
        self.viewer = User.objects.create_user(
            username="story-viewer",
            email="story-viewer@example.com",
            password="test-password-123",
        )

    def create_story(self):
        # A stored file name avoids external media uploads during this model test.
        return Story.objects.create(
            author=self.author,
            image="stories/images/test-story.jpg",
        )

    def test_story_lifetime_is_exactly_five_hours(self):
        story = self.create_story()

        self.assertEqual(STORY_LIFETIME, timedelta(hours=5))
        self.assertEqual(
            story.expires_at - story.created_at,
            timedelta(hours=5),
        )

    def test_active_queryset_excludes_expired_story(self):
        story = self.create_story()
        Story.objects.filter(pk=story.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        self.assertFalse(Story.objects.active().filter(pk=story.pk).exists())
        self.assertTrue(Story.objects.expired().filter(pk=story.pk).exists())

    def test_viewer_receipt_is_unique_per_story_and_user(self):
        story = self.create_story()
        StoryView.objects.create(story=story, viewer=self.viewer)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StoryView.objects.create(story=story, viewer=self.viewer)

    def test_cleanup_command_removes_expired_story(self):
        story = self.create_story()
        Story.objects.filter(pk=story.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        call_command("cleanup_expired_stories")

        self.assertFalse(Story.objects.filter(pk=story.pk).exists())
