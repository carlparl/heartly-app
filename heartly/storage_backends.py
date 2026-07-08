"""
Cloudinary storage backend for Heartly media.

Why this exists:
- django-cloudinary-storage's default MediaCloudinaryStorage uploads as image.
- Feed videos must be uploaded to Cloudinary with resource_type="video".
- Other files should fall back to Cloudinary raw resources.
"""

from pathlib import Path

from cloudinary_storage.storage import MediaCloudinaryStorage, RESOURCE_TYPES


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


class AutoResourceCloudinaryStorage(MediaCloudinaryStorage):
    """
    Pick the Cloudinary resource type from the file extension.

    Images -> image
    Videos -> video
    Other files -> raw
    """

    def _get_resource_type(self, name):
        extension = Path(str(name)).suffix.lower()

        if extension in VIDEO_EXTENSIONS:
            return RESOURCE_TYPES["VIDEO"]

        if extension in IMAGE_EXTENSIONS:
            return RESOURCE_TYPES["IMAGE"]

        return RESOURCE_TYPES["RAW"]
