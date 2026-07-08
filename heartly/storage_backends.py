import os
from pathlib import Path

import cloudinary
import cloudinary.uploader
import requests
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile

from cloudinary_storage.storage import MediaCloudinaryStorage


class AutoResourceCloudinaryStorage(MediaCloudinaryStorage):
    """
    Cloudinary media storage for mixed Heartly uploads.

    Why this exists:
    - django-cloudinary-storage's MediaCloudinaryStorage uploads as image by default.
    - Heartly uploads images, videos, and files through the same default storage.
    - Videos must be uploaded to Cloudinary as resource_type="video", not "image".

    The saved database value is prefixed with a small marker so url/delete/open
    can later use the correct Cloudinary resource type.
    """

    IMAGE_EXTENSIONS = {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
        ".bmp",
        ".tiff",
        ".svg",
    }

    VIDEO_EXTENSIONS = {
        ".mp4",
        ".webm",
        ".mov",
        ".m4v",
        ".3gp",
        ".3gpp",
        ".3gpp2",
        ".avi",
        ".mkv",
    }

    RAW_EXTENSIONS = {
        ".pdf",
        ".txt",
        ".zip",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".csv",
    }

    TYPE_MARKERS = {
        "image": "__image__/",
        "video": "__video__/",
        "raw": "__raw__/",
    }

    def _file_extension(self, name):
        return Path(str(name or "")).suffix.lower().strip()

    def _detect_resource_type(self, name):
        extension = self._file_extension(name)

        if extension in self.VIDEO_EXTENSIONS:
            return "video"

        if extension in self.RAW_EXTENSIONS:
            return "raw"

        return "image"

    def _split_marker(self, name):
        clean_name = str(name or "").replace("\\", "/")

        for resource_type, marker in self.TYPE_MARKERS.items():
            if clean_name.startswith(marker):
                return resource_type, clean_name[len(marker):]

        return self._detect_resource_type(clean_name), clean_name

    def _marker_for(self, resource_type):
        return self.TYPE_MARKERS.get(resource_type, self.TYPE_MARKERS["image"])

    def _upload_with_resource_type(self, name, content, resource_type):
        options = {
            "use_filename": True,
            "resource_type": resource_type,
            "tags": self.TAG,
        }

        folder = os.path.dirname(name)
        if folder:
            options["folder"] = folder

        return cloudinary.uploader.upload(content, **options)

    def _save(self, name, content):
        name = self._normalise_name(name)
        resource_type = self._detect_resource_type(name)
        name = self._prepend_prefix(name)

        uploaded_file = UploadedFile(content, name)
        response = self._upload_with_resource_type(name, uploaded_file, resource_type)

        public_id = response["public_id"]
        return f"{self._marker_for(resource_type)}{public_id}"

    def _get_url(self, name):
        resource_type, public_id = self._split_marker(name)

        cloudinary_resource = cloudinary.CloudinaryResource(
            public_id,
            default_resource_type=resource_type,
        )

        return cloudinary_resource.url

    def url(self, name):
        return self._get_url(name)

    def delete(self, name):
        resource_type, public_id = self._split_marker(name)

        response = cloudinary.uploader.destroy(
            public_id,
            invalidate=True,
            resource_type=resource_type,
        )

        return response.get("result") == "ok"

    def exists(self, name):
        response = requests.head(self._get_url(name))

        if response.status_code == 404:
            return False

        response.raise_for_status()
        return True

    def size(self, name):
        response = requests.head(self._get_url(name))

        if response.status_code == 200:
            return int(response.headers.get("content-length", 0))

        return None

    def _open(self, name, mode="rb"):
        response = requests.get(self._get_url(name))

        if response.status_code == 404:
            raise IOError

        response.raise_for_status()

        file = ContentFile(response.content)
        file.name = name
        file.mode = mode

        return file
