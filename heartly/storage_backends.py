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

    Cloudinary removes the extension from saved image and video public IDs.
    The known folder paths therefore remain the reliable source of truth when
    Django later asks this storage class to rebuild a media URL.
    """

    def _get_resource_type(self, name):
        normalized_name = str(name or "").replace("\\", "/").lower()
        suffix = Path(normalized_name).suffix.lower()

        image_paths = (
            "feed/images/",
            "stories/images/",
            "chat/images/",
            "profiles/",
            "profile/",
            "profile_pictures/",
            "avatars/",
            "users/",
        )

        video_paths = (
            "feed/videos/",
            "stories/videos/",
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
