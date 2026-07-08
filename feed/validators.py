from pathlib import Path

from django.conf import settings


ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}

ALLOWED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
}

ALLOWED_VIDEO_CONTENT_TYPES = {
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/x-m4v",
    "video/3gpp",
    "video/3gpp2",
}

ALLOWED_VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".m4v",
    ".webm",
    ".3gp",
    ".3g2",
}

DEFAULT_MAX_IMAGE_SIZE = 15 * 1024 * 1024
DEFAULT_MAX_VIDEO_SIZE = 60 * 1024 * 1024


def _extension(uploaded_file):
    return Path(getattr(uploaded_file, "name", "") or "").suffix.lower()


def _content_type(uploaded_file):
    return (getattr(uploaded_file, "content_type", "") or "").lower()


def validate_image_upload(uploaded_file):
    if not uploaded_file:
        return None

    content_type = _content_type(uploaded_file)
    extension = _extension(uploaded_file)
    max_size = int(getattr(settings, "HEARTLY_MAX_IMAGE_UPLOAD_SIZE", DEFAULT_MAX_IMAGE_SIZE))

    if content_type not in ALLOWED_IMAGE_CONTENT_TYPES and extension not in ALLOWED_IMAGE_EXTENSIONS:
        return "Invalid image file. Please upload JPG, PNG, WEBP, or GIF."

    if uploaded_file.size > max_size:
        return "Image is too large. Please upload a smaller image."

    return None


def validate_video_upload(uploaded_file):
    if not uploaded_file:
        return None

    content_type = _content_type(uploaded_file)
    extension = _extension(uploaded_file)
    max_size = int(getattr(settings, "HEARTLY_MAX_VIDEO_UPLOAD_SIZE", DEFAULT_MAX_VIDEO_SIZE))

    if content_type not in ALLOWED_VIDEO_CONTENT_TYPES and extension not in ALLOWED_VIDEO_EXTENSIONS:
        return "Invalid video file. Please upload MP4, MOV, M4V, WEBM, 3GP, or 3G2."

    if uploaded_file.size > max_size:
        return "Video is too large. Please upload a smaller video."

    return None
