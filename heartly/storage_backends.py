from pathlib import Path

from cloudinary_storage.storage import MediaCloudinaryStorage


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
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
}


class AutoResourceCloudinaryStorage(MediaCloudinaryStorage):
    """
    Heartly Cloudinary media storage.

    Forces images to Cloudinary image resources,
    videos to Cloudinary video resources,
    and everything else to raw.
    """

    def _get_resource_type(self, name):
        normalized_name = str(name or "").lower()
        suffix = Path(normalized_name).suffix.lower()

        image_paths = (
            "feed/images/",
            "chat/images/",
            "profiles/",
            "profile/",
            "profile_pictures/",
            "avatars/",
            "users/",
        )

        video_paths = (
            "feed/videos/",
            "chat/videos/",
        )

        if any(path in normalized_name for path in image_paths):
            return "image"

        if any(path in normalized_name for path in video_paths):
            return "video"

        if suffix in IMAGE_EXTENSIONS:
            return "image"

        if suffix in VIDEO_EXTENSIONS:
            return "video"

        return "raw"