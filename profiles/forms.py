import os

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.validators import UnicodeUsernameValidator

from .models import Interest, Profile


MAX_PROFILE_PHOTO_SIZE = 5 * 1024 * 1024
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def get_file_extension(uploaded_file):
    filename = uploaded_file.name or ""
    return os.path.splitext(filename.lower())[1]


class ProfileForm(forms.ModelForm):
    username = forms.CharField(
        label="Username",
        required=True,
        validators=[UnicodeUsernameValidator()],
        widget=forms.TextInput(
            attrs={
                "placeholder": "@username",
                "maxlength": "150",
                "autocomplete": "username",
            }
        ),
    )

    class Meta:
        model = Profile
        fields = [
            "profile_picture",
            "display_name",
            "username",
            "bio",
            "gender",
            "interested_in",
        ]

        widgets = {
            "profile_picture": forms.FileInput(
                attrs={
                    "class": "heartly-file-input",
                    "accept": "image/jpeg,image/png,image/webp,image/gif",
                }
            ),
            "display_name": forms.TextInput(
                attrs={
                    "placeholder": "Full name",
                    "maxlength": "80",
                    "autocomplete": "name",
                }
            ),
            "bio": forms.Textarea(
                attrs={
                    "placeholder": "Coffee lover ☕ | Travel enthusiast ✈️ | Good vibes only ✨",
                    "rows": 3,
                    "maxlength": "150",
                }
            ),
            "gender": forms.Select(
                attrs={
                    "class": "profile-select",
                }
            ),
            "interested_in": forms.Select(
                attrs={
                    "class": "profile-select",
                }
            ),
        }

        labels = {
            "profile_picture": "Profile photo",
            "display_name": "Full name",
            "bio": "Bio",
            "gender": "Gender",
            "interested_in": "Interested in",
        }

        help_texts = {
            "bio": "Keep it friendly and safe. Do not share private contact details.",
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user or getattr(self.instance, "user", None)

        if self.user is not None:
            self.fields["username"].initial = getattr(self.user, "username", "") or ""

        self.fields["gender"].choices = [("", "Choose gender")] + list(Profile.GENDER_CHOICES)
        self.fields["interested_in"].choices = [("", "Choose preference")] + list(Profile.INTERESTED_IN_CHOICES)

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
                "Profile photo is too large. Maximum size is 5MB."
            )

        return photo

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()

        if username.startswith("@"):
            username = username[1:].strip()

        if not username:
            raise forms.ValidationError("Username is required.")

        User = get_user_model()
        username_field = User._meta.get_field("username")
        max_length = getattr(username_field, "max_length", 150) or 150

        if len(username) > max_length:
            raise forms.ValidationError(
                f"Username cannot be longer than {max_length} characters."
            )

        query = User.objects.filter(username__iexact=username)

        if self.user is not None:
            query = query.exclude(pk=self.user.pk)

        if query.exists():
            raise forms.ValidationError("This username is already taken.")

        return username

    def clean_bio(self):
        bio = (self.cleaned_data.get("bio") or "").strip()

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

    def save(self, commit=True):
        profile = super().save(commit=False)
        username = self.cleaned_data.get("username")

        if commit:
            profile.save()

            if self.user is not None and username and getattr(self.user, "username", "") != username:
                self.user.username = username
                self.user.save(update_fields=["username"])

            self.save_m2m()

        return profile


class InterestForm(forms.Form):
    interests = forms.ModelMultipleChoiceField(
        queryset=Interest.objects.all().order_by("name"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Interests",
    )
