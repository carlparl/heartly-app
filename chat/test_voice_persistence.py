from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from chat.models import ChatAttachment
from chat.views import (
    playable_file_url,
    upload_voice_note_to_cloudinary,
)


@override_settings(
    MEDIA_STORAGE_BACKEND="cloudinary",
    CLOUDINARY_STORAGE={
        "CLOUD_NAME": "test-cloud",
        "API_KEY": "test-key",
        "API_SECRET": "test-secret",
    },
)
class VoicePersistenceUrlTests(SimpleTestCase):
    @patch("chat.views.ensure_cloudinary_configured")
    @patch("chat.views.cloudinary_voice_upload_is_available", return_value=True)
    @patch("chat.views.cloudinary_uploader.upload")
    def test_cloudinary_delivery_url_is_not_rewritten(
        self,
        mocked_upload,
        _available,
        _configured,
    ):
        mocked_upload.return_value = {
            "secure_url": (
                "https://res.cloudinary.com/test-cloud/"
                "video/upload/v1/media/chat/voice-note.mp4"
            ),
            "public_id": "media/chat/voice-note",
            "format": "mp4",
        }
        voice_file = SimpleUploadedFile(
            "heartly-voice-note.m4a",
            b"voice-data",
            content_type="audio/mp4",
        )

        result = upload_voice_note_to_cloudinary(
            voice_file
        )

        self.assertEqual(
            result["url"],
            mocked_upload.return_value["secure_url"],
        )
        self.assertFalse(
            result["url"].endswith(".mp4.m4a")
        )
        self.assertEqual(
            result["content_type"],
            "audio/mp4",
        )

    def test_saved_external_url_is_returned_unchanged(self):
        attachment = SimpleNamespace(
            attachment_type=ChatAttachment.TYPE_AUDIO,
            external_url=(
                "https://res.cloudinary.com/test-cloud/"
                "video/upload/v1/media/chat/voice-note.mp4"
            ),
            file=None,
            original_filename="heartly-voice-note.m4a",
        )

        self.assertEqual(
            playable_file_url(attachment),
            attachment.external_url,
        )

    def test_previous_double_extension_is_repaired_at_playback(self):
        attachment = SimpleNamespace(
            attachment_type=ChatAttachment.TYPE_AUDIO,
            external_url=(
                "https://res.cloudinary.com/test-cloud/"
                "video/upload/v1/media/chat/voice-note.mp4.m4a"
                "?version=1"
            ),
            file=None,
            original_filename="heartly-voice-note.m4a",
        )

        self.assertEqual(
            playable_file_url(attachment),
            (
                "https://res.cloudinary.com/test-cloud/"
                "video/upload/v1/media/chat/voice-note.mp4"
                "?version=1"
            ),
        )
