from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class FeedEditPreviewContractTests(SimpleTestCase):
    def read_source(self, relative_path):
        return (
            Path(settings.BASE_DIR) / relative_path
        ).read_text(encoding="utf-8")

    def test_edit_template_contains_preview_controls(self):
        source = self.read_source(
            "templates/feed/_post_card.html"
        )

        self.assertIn("data-edit-preview", source)
        self.assertIn("data-edit-preview-caption", source)
        self.assertIn("data-edit-preview-media", source)
        self.assertIn("data-edit-image-input", source)
        self.assertIn("data-edit-video-input", source)
        self.assertIn("data-edit-remove-image", source)
        self.assertIn("data-edit-remove-video", source)

    def test_edit_javascript_renders_media_preview(self):
        source = self.read_source(
            "static/js/heartly-feed-ajax.js"
        )

        self.assertIn(
            "renderEditMediaPreview",
            source,
        )
        self.assertIn(
            "updateEditCaptionPreview",
            source,
        )
        self.assertIn(
            "revokeEditPreviewUrl",
            source,
        )
        self.assertIn(
            "data-edit-image-input",
            source,
        )
        self.assertIn(
            "data-edit-video-input",
            source,
        )
        self.assertIn(
            'document.addEventListener(\n    "change"',
            source,
        )
        self.assertIn(
            'document.addEventListener(\n    "input"',
            source,
        )

    def test_edit_preview_styles_exist(self):
        source = self.read_source(
            "templates/feed/feed.html"
        )

        self.assertIn(
            ".edit-live-preview",
            source,
        )
        self.assertIn(
            ".edit-preview-media",
            source,
        )
        self.assertIn(
            ".edit-preview-status",
            source,
        )
