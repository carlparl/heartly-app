import os

from django import forms

from .models import Interest, Profile


MAX_PROFILE_PHOTO_SIZE = 8 * 1024 * 1024
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def get_file_extension(uploaded_file):
    filename = uploaded_file.name or ""
    return os.path.splitext(filename.lower())[1]


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            "profile_picture",
            "display_name",
            "age",
            "location",
            "bio",
        ]

        widgets = {
            "profile_picture": forms.ClearableFileInput(
                attrs={
                    "class": "heartly-file-input",
                    "accept": "image/*",
                }
            ),
            "display_name": forms.TextInput(
                attrs={
                    "placeholder": "Your display name",
                    "maxlength": "80",
                }
            ),
            "age": forms.NumberInput(
                attrs={
                    "placeholder": "Your age",
                    "min": "13",
                    "max": "120",
                }
            ),
            "location": forms.TextInput(
                attrs={
                    "placeholder": "City or general area",
                    "maxlength": "120",
                }
            ),
            "bio": forms.Textarea(
                attrs={
                    "placeholder": "Write a short, friendly bio. Avoid private details like exact address, school schedule, or phone number.",
                    "rows": 5,
                    "maxlength": "500",
                }
            ),
        }

        labels = {
            "profile_picture": "Profile photo",
            "display_name": "Display name",
            "age": "Age",
            "location": "Location",
            "bio": "Bio",
        }

        help_texts = {
            "location": "Use a general location, not your exact address.",
            "bio": "Keep it friendly and safe. Do not share private contact details.",
        }

    def clean_profile_picture(self):
        photo = self.cleaned_data.get("profile_picture")

        if not photo:
            return photo

        extension = get_file_extension(photo)

        if extension not in IMAGE_EXTENSIONS:
            raise forms.ValidationError(
                "Unsupported image type. Use JPG, PNG, GIF, or WEBP."
            )

        if photo.size > MAX_PROFILE_PHOTO_SIZE:
            raise forms.ValidationError(
                "Profile photo is too large. Maximum size is 8MB."
            )

        return photo

    def clean_age(self):
        age = self.cleaned_data.get("age")

        if age is None:
            return age

        if age < 13:
            raise forms.ValidationError("You must be at least 13 to use Heartly.")

        if age > 120:
            raise forms.ValidationError("Enter a valid age.")

        return age

    def clean_bio(self):
        bio = self.cleaned_data.get("bio", "").strip()

        blocked_phrases = [
            "password",
            "home address",
            "exact address",
            "phone number",
            "school schedule",
        ]

        lowered_bio = bio.lower()

        for phrase in blocked_phrases:
            if phrase in lowered_bio:
                raise forms.ValidationError(
                    "Do not include private information in your bio."
                )

        return bio


class InterestForm(forms.Form):
    interests = forms.ModelMultipleChoiceField(
        queryset=Interest.objects.all().order_by("name"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Interests",
    )