from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class StoryPlaybackContractTests(SimpleTestCase):
    def read_source(self, relative_path):
        return (
            Path(settings.BASE_DIR) / relative_path
        ).read_text(encoding="utf-8")

    def test_story_template_has_authoritative_hooks(self):
        source = self.read_source(
            "templates/feed/story_detail.html"
        )

        self.assertIn("data-story-viewer", source)
        self.assertIn(
            "data-story-progress-fill",
            source,
        )
        self.assertIn(
            "data-story-media-stage",
            source,
        )
        self.assertIn(
            "data-story-previous-url",
            source,
        )
        self.assertIn(
            "data-story-close-url",
            source,
        )

    def test_story_template_uses_external_controller(self):
        source = self.read_source(
            "templates/feed/story_detail.html"
        )

        self.assertIn(
            "js/heartly-story-viewer.js",
            source,
        )
        self.assertNotIn(
            "window.setTimeout(advanceStory",
            source,
        )

    def test_story_controller_pauses_in_background(self):
        source = self.read_source(
            "static/js/heartly-story-viewer.js"
        )

        self.assertIn(
            "handleVisibilityChange",
            source,
        )
        self.assertIn("pauseTimer", source)
        self.assertIn("resumeTimer", source)
        self.assertIn(
            "pauseVideoForVisibility",
            source,
        )
        self.assertIn(
            "resumeVideoFromVisibility",
            source,
        )

    def test_story_controller_prevents_duplicate_playback(self):
        source = self.read_source(
            "static/js/heartly-story-viewer.js"
        )

        self.assertIn("cancelTimer", source)
        self.assertIn("cancelAnimation", source)
        self.assertIn("isAdvancing", source)
        self.assertIn("isDestroyed", source)
        self.assertIn("pagehide", source)

    def test_video_progress_uses_media_duration(self):
        source = self.read_source(
            "static/js/heartly-story-viewer.js"
        )

        self.assertIn("video.duration", source)
        self.assertIn("video.currentTime", source)
        self.assertIn(
            'video.addEventListener(\n      "ended"',
            source,
        )

    def test_image_timer_starts_after_load(self):
        source = self.read_source(
            "static/js/heartly-story-viewer.js"
        )

        self.assertIn(
            'image.addEventListener(\n      "load"',
            source,
        )
        self.assertIn(
            "startPhotoPlayback",
            source,
        )
        self.assertIn(
            "image.naturalWidth",
            source,
        )
