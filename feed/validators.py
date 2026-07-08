from pathlib import Path

from django.conf import settings


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".avif",
    ".heic",
    ".heif",
}

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".m4v",
    ".webm",
    ".3gp",
    ".3g2",
    ".avi",
    ".mkv",
    ".mpeg",
    ".mpg",
    ".ogv",
}

IMAGE_MIME_PREFIXES = ("image/",)
VIDEO_MIME_PREFIXES = ("video/",)

# Mobile browsers sometimes send empty MIME or application/octet-stream.
FALLBACK_MIME_TYPES = {"", "application/octet-stream"}

MAX_IMAGE_SIZE = int(getattr(settings, "HEARTLY_MAX_IMAGE_UPLOAD_SIZE", 15 * 1024 * 1024))
MAX_VIDEO_SIZE = int(getattr(settings, "HEARTLY_MAX_VIDEO_UPLOAD_SIZE", 60 * 1024 * 1024))


def upload_extension(upload):
    return Path(getattr(upload, "name", "")).suffix.lower()


def upload_content_type(upload):
    return (getattr(upload, "content_type", "") or "").lower()


def valid_image_upload(upload):
    if not upload:
        return True

    ext = upload_extension(upload)
    content_type = upload_content_type(upload)

    if ext not in IMAGE_EXTENSIONS:
        return False

    return content_type.startswith(IMAGE_MIME_PREFIXES) or content_type in FALLBACK_MIME_TYPES


def valid_video_upload(upload):
    if not upload:
        return True

    ext = upload_extension(upload)
    content_type = upload_content_type(upload)

    if ext not in VIDEO_EXTENSIONS:
        return False

    return content_type.startswith(VIDEO_MIME_PREFIXES) or content_type in FALLBACK_MIME_TYPES


def validate_feed_uploads(*, image=None, video=None):
    """
    Returns (ok, message). Keeps image and video validation fully separate.
    """

    if image and video:
        return False, "Choose either a photo or a video, not both."

    if image:
        if image.size > MAX_IMAGE_SIZE:
            return False, "Image is too large. Please upload an image under 15MB."

        if not valid_image_upload(image):
            return False, "Invalid photo file. Please upload JPG, PNG, WEBP, GIF, AVIF, HEIC, or HEIF."

    if video:
        if video.size > MAX_VIDEO_SIZE:
            return False, "Video is too large. Please upload a video under 60MB."

        if not valid_video_upload(video):
            return False, "Invalid video file. Please upload MP4, MOV, M4V, WEBM, 3GP, 3G2, AVI, MKV, MPEG, or OGV."

    return True, ""
