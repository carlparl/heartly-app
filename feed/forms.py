import os

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from .models import Post, PostReport, Story


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}

MAX_IMAGE_SIZE_MB = 10
MAX_VIDEO_SIZE_MB = 100
STORY_MAX_IMAGE_SIZE_MB = min(
    MAX_IMAGE_SIZE_MB,
    max(1, getattr(settings, "HEARTLY_MAX_IMAGE_UPLOAD_SIZE", 15 * 1024 * 1024) // (1024 * 1024)),
)
STORY_MAX_VIDEO_SIZE_MB = min(
    MAX_VIDEO_SIZE_MB,
    max(1, getattr(settings, "HEARTLY_MAX_VIDEO_UPLOAD_SIZE", 60 * 1024 * 1024) // (1024 * 1024)),
)


def validate_uploaded_file(file, allowed_extensions, max_size_mb, file_type_name):
    """
    Validates uploaded file extension and file size.
    This prevents bad uploads before Cloudinary/local storage receives them.
    """
    if not file:
        return file

    ext = os.path.splitext(file.name)[1].lower()

    if ext not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise ValidationError(
            f"Invalid {file_type_name} format. Allowed formats: {allowed}"
        )

    max_size_bytes = max_size_mb * 1024 * 1024

    if file.size > max_size_bytes:
        raise ValidationError(
            f"{file_type_name.capitalize()} must be smaller than {max_size_mb}MB."
        )

    return file


class BasePostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ["content", "image", "video"]

    def clean_image(self):
        image = self.cleaned_data.get("image")
        return validate_uploaded_file(
            image,
            ALLOWED_IMAGE_EXTENSIONS,
            MAX_IMAGE_SIZE_MB,
            "image",
        )

    def clean_video(self):
        video = self.cleaned_data.get("video")
        return validate_uploaded_file(
            video,
            ALLOWED_VIDEO_EXTENSIONS,
            MAX_VIDEO_SIZE_MB,
            "video",
        )

    def clean(self):
        cleaned_data = super().clean()

        content = cleaned_data.get("content")
        image = cleaned_data.get("image")
        video = cleaned_data.get("video")

        existing_image = getattr(self.instance, "image", None)
        existing_video = getattr(self.instance, "video", None)

        has_content = bool(content and content.strip())
        has_image = bool(image or existing_image)
        has_video = bool(video or existing_video)

        if not has_content and not has_image and not has_video:
            raise ValidationError(
                "Add text, an image, or a video before posting."
            )

        return cleaned_data


class PostForm(BasePostForm):
    class Meta(BasePostForm.Meta):
        widgets = {
            "content": forms.Textarea(attrs={
                "class": "composer-textarea",
                "placeholder": "What do you want to share?",
                "rows": 4,
            }),
            "image": forms.ClearableFileInput(attrs={
                "class": "composer-file-input",
                "accept": "image/jpeg,image/png,image/webp",
            }),
            "video": forms.ClearableFileInput(attrs={
                "class": "composer-file-input",
                "accept": "video/mp4,video/quicktime,video/webm",
            }),
        }


class EditPostForm(BasePostForm):
    class Meta(BasePostForm.Meta):
        widgets = {
            "content": forms.Textarea(attrs={
                "class": "edit-textarea",
                "placeholder": "Update your post...",
                "rows": 5,
            }),
            "image": forms.ClearableFileInput(attrs={
                "class": "edit-file-input",
                "accept": "image/jpeg,image/png,image/webp",
            }),
            "video": forms.ClearableFileInput(attrs={
                "class": "edit-file-input",
                "accept": "video/mp4,video/quicktime,video/webm",
            }),
        }


class StoryForm(forms.ModelForm):
    class Meta:
        model = Story
        fields = ["caption", "image", "video"]
        widgets = {
            "caption": forms.Textarea(attrs={
                "class": "story-caption-input",
                "placeholder": "Add a short caption (optional)",
                "rows": 3,
                "maxlength": 280,
            }),
            "image": forms.ClearableFileInput(attrs={
                "class": "story-file-input",
                "accept": "image/jpeg,image/png,image/webp",
            }),
            "video": forms.ClearableFileInput(attrs={
                "class": "story-file-input",
                "accept": "video/mp4,video/quicktime,video/webm",
            }),
        }

    def clean_image(self):
        image = self.cleaned_data.get("image")
        return validate_uploaded_file(
            image,
            ALLOWED_IMAGE_EXTENSIONS,
            STORY_MAX_IMAGE_SIZE_MB,
            "image",
        )

    def clean_video(self):
        video = self.cleaned_data.get("video")
        return validate_uploaded_file(
            video,
            ALLOWED_VIDEO_EXTENSIONS,
            STORY_MAX_VIDEO_SIZE_MB,
            "video",
        )

    def clean_caption(self):
        return (self.cleaned_data.get("caption") or "").strip()

    def clean(self):
        cleaned_data = super().clean()
        image = cleaned_data.get("image")
        video = cleaned_data.get("video")

        if bool(image) == bool(video):
            raise ValidationError("Choose one photo or one video for your Story.")

        return cleaned_data


class PostReportForm(forms.ModelForm):
    class Meta:
        model = PostReport
        fields = ["reason", "details"]
        widgets = {
            "reason": forms.Select(attrs={
                "class": "report-select",
            }),
            "details": forms.Textarea(attrs={
                "class": "report-textarea",
                "placeholder": "Add more details. Optional.",
                "rows": 3,
            }),
        }
