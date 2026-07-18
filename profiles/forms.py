import os
from datetime import timedelta

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import transaction

from .identity import (
    MAXIMUM_LEGAL_AGE,
    MINIMUM_LEGAL_AGE,
    age_from_date_of_birth,
    legal_birth_date_bounds,
    mapped_profile_gender,
    mapped_profile_preference,
    mapped_user_gender,
    mapped_user_preference,
)
from .models import Interest, Profile


MAX_PROFILE_PHOTO_SIZE = 5 * 1024 * 1024
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

PROFILE_TO_USER_GENDER = {
    "man": "male",
    "woman": "female",
    "non_binary": "non_binary",
    "other": "prefer_not_to_say",
}

PROFILE_TO_USER_INTERESTED_IN = {
    "men": "male",
    "women": "female",
    "everyone": "both",
}


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
            "connection_goal",
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
                    "placeholder": "Coffee lover | Travel enthusiast | Good vibes only",
                    "rows": 3,
                    "maxlength": "150",
                }
            ),
            "gender": forms.Select(
                attrs={
                    "class": "profile-select",
                }
            ),
            "connection_goal": forms.Select(
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
            "connection_goal": "Looking for",
            "interested_in": "Who you want to meet",
        }

        help_texts = {
            "bio": "Keep it friendly and safe. Do not share private contact details.",
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user or getattr(self.instance, "user", None)

        if self.user is not None:
            self.fields["username"].initial = (
                getattr(self.user, "username", "") or ""
            )

        self.fields["gender"].choices = [
            ("", "Choose gender"),
        ] + list(Profile.GENDER_CHOICES)

        self.fields["connection_goal"].choices = [
            ("", "Choose what you are looking for"),
        ] + list(Profile.CONNECTION_GOAL_CHOICES)

        self.fields["interested_in"].choices = [
            ("", "Choose who you want to meet"),
        ] + list(Profile.INTERESTED_IN_CHOICES)

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
        display_name = (
            self.cleaned_data.get("display_name") or ""
        ).strip()

        if self.user is not None and self.user.date_of_birth:
            profile.age = self.user.age

        if not commit:
            return profile

        with transaction.atomic():
            profile.save()

            if self.user is not None:
                name_parts = display_name.split()

                self.user.username = username
                self.user.full_name = display_name
                self.user.first_name = name_parts[0] if name_parts else ""
                self.user.last_name = (
                    " ".join(name_parts[1:])
                    if len(name_parts) > 1
                    else ""
                )
                self.user.gender = PROFILE_TO_USER_GENDER.get(
                    profile.gender,
                    "",
                )
                self.user.interested_in = (
                    PROFILE_TO_USER_INTERESTED_IN.get(
                        profile.interested_in,
                        "",
                    )
                )
                self.user.save()

            self.save_m2m()

        return profile


class IdentityRepairForm(forms.Form):
    display_name = forms.CharField(
        label="Name shown on Heartly",
        max_length=120,
        required=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Your display name",
                "autocomplete": "name",
            }
        ),
    )
    date_of_birth = forms.DateField(
        label="Date of birth",
        required=True,
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={
                "type": "date",
                "autocomplete": "bday",
            },
        ),
    )
    gender = forms.ChoiceField(
        label="Gender",
        required=True,
    )
    connection_goal = forms.ChoiceField(
        label="Looking for",
        required=True,
    )
    interested_in = forms.ChoiceField(
        label="Who you want to meet",
        required=True,
    )

    def __init__(self, *args, user, profile, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.profile = profile

        oldest_exclusive, youngest_inclusive = (
            legal_birth_date_bounds()
        )
        oldest_inclusive = oldest_exclusive + timedelta(days=1)

        self.fields["date_of_birth"].widget.attrs.update(
            {
                "min": oldest_inclusive.isoformat(),
                "max": youngest_inclusive.isoformat(),
            }
        )
        self.fields["gender"].choices = [
            ("", "Choose gender"),
            *Profile.GENDER_CHOICES,
        ]
        self.fields["connection_goal"].choices = [
            ("", "Choose what you are looking for"),
            *Profile.CONNECTION_GOAL_CHOICES,
        ]
        self.fields["interested_in"].choices = [
            ("", "Choose who you want to meet"),
            *Profile.INTERESTED_IN_CHOICES,
        ]

        if not self.is_bound:
            valid_genders = {
                value for value, _label in Profile.GENDER_CHOICES
            }
            valid_preferences = {
                value
                for value, _label in Profile.INTERESTED_IN_CHOICES
            }
            valid_goals = {
                value
                for value, _label in Profile.CONNECTION_GOAL_CHOICES
            }

            profile_gender = (profile.gender or "").strip()
            if profile_gender not in valid_genders:
                profile_gender = (
                    mapped_profile_gender(user.gender) or ""
                )

            profile_preference = (
                profile.interested_in or ""
            ).strip()
            if profile_preference not in valid_preferences:
                profile_preference = (
                    mapped_profile_preference(
                        user.interested_in
                    )
                    or ""
                )

            connection_goal = (
                profile.connection_goal or ""
            ).strip()
            if connection_goal not in valid_goals:
                connection_goal = ""

            self.initial.update(
                {
                    "display_name": (
                        profile.display_name
                        or user.full_name
                        or user.get_full_name()
                        or ""
                    ),
                    "date_of_birth": user.date_of_birth,
                    "gender": profile_gender,
                    "connection_goal": connection_goal,
                    "interested_in": profile_preference,
                }
            )

    def clean_display_name(self):
        display_name = (
            self.cleaned_data.get("display_name") or ""
        ).strip()

        if not display_name:
            raise forms.ValidationError(
                "Enter the name you want people to see."
            )

        return display_name

    def clean_date_of_birth(self):
        date_of_birth = self.cleaned_data["date_of_birth"]
        age = age_from_date_of_birth(date_of_birth)

        if age is None or not (
            MINIMUM_LEGAL_AGE
            <= age
            <= MAXIMUM_LEGAL_AGE
        ):
            raise forms.ValidationError(
                "Heartly Discover is available only to confirmed "
                "adults between 18 and 100."
            )

        return date_of_birth

    def save(self):
        display_name = self.cleaned_data["display_name"]
        date_of_birth = self.cleaned_data["date_of_birth"]
        profile_gender = self.cleaned_data["gender"]
        connection_goal = self.cleaned_data["connection_goal"]
        profile_preference = self.cleaned_data["interested_in"]

        user_gender = mapped_user_gender(profile_gender)
        user_preference = mapped_user_preference(
            profile_preference
        )

        if not user_gender or not user_preference:
            raise ValueError(
                "Identity selections could not be synchronized."
            )

        age = age_from_date_of_birth(date_of_birth)
        name_parts = display_name.split()

        with transaction.atomic():
            self.profile.display_name = display_name
            self.profile.age = age
            self.profile.gender = profile_gender
            self.profile.connection_goal = connection_goal
            self.profile.interested_in = profile_preference
            self.profile.save(
                update_fields=[
                    "display_name",
                    "age",
                    "gender",
                    "connection_goal",
                    "interested_in",
                    "updated_at",
                ]
            )

            self.user.full_name = display_name
            self.user.first_name = (
                name_parts[0] if name_parts else ""
            )
            self.user.last_name = (
                " ".join(name_parts[1:])
                if len(name_parts) > 1
                else ""
            )
            self.user.date_of_birth = date_of_birth
            self.user.gender = user_gender
            self.user.interested_in = user_preference
            self.user.save(
                update_fields=[
                    "full_name",
                    "first_name",
                    "last_name",
                    "date_of_birth",
                    "gender",
                    "interested_in",
                    "updated_at",
                ]
            )

        return self.profile

class InterestForm(forms.Form):
    interests = forms.ModelMultipleChoiceField(
        queryset=Interest.objects.all().order_by("name"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Interests",
    )
