from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from profiles.identity import (
    MAXIMUM_LEGAL_AGE,
    MINIMUM_LEGAL_AGE,
    age_from_date_of_birth,
    legal_birth_date_bounds,
    mapped_profile_gender,
    mapped_profile_preference,
)

from profiles.models import Profile

from .models import CustomUser


SIGNUP_INTERESTED_IN_CHOICES = [
    choice
    for choice in CustomUser.INTERESTED_IN_CHOICES
    if choice[0] != "friends"
]


class CustomSignupForm(forms.Form):
    full_name = forms.CharField(
        max_length=150,
        required=True,
        label="Full name",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Your full name",
                "autocomplete": "name",
                "class": "heartly-input",
            }
        ),
    )

    phone_number = forms.CharField(
        max_length=20,
        required=False,
        label="Phone number",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Optional phone number",
                "autocomplete": "tel",
                "class": "heartly-input",
            }
        ),
    )

    gender = forms.ChoiceField(
        choices=[
            ("", "Select your gender"),
            *CustomUser.GENDER_CHOICES,
        ],
        required=True,
        label="Gender",
        widget=forms.Select(
            attrs={
                "class": "heartly-input",
            }
        ),
    )

    connection_goal = forms.ChoiceField(
        choices=[
            ("", "What are you looking for?"),
            *Profile.CONNECTION_GOAL_CHOICES,
        ],
        required=True,
        label="Looking for",
        widget=forms.Select(
            attrs={
                "class": "heartly-input",
            }
        ),
    )

    interested_in = forms.ChoiceField(
        choices=[
            ("", "Who are you interested in?"),
            *SIGNUP_INTERESTED_IN_CHOICES,
        ],
        required=True,
        label="Interested in",
        widget=forms.Select(
            attrs={
                "class": "heartly-input",
            }
        ),
    )

    date_of_birth = forms.DateField(
        required=True,
        label="Date of birth",
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={
                "type": "date",
                "autocomplete": "bday",
                "class": "heartly-input",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        oldest_exclusive, youngest_inclusive = (
            legal_birth_date_bounds()
        )

        self.fields["date_of_birth"].widget.attrs.update(
            {
                "min": (
                    oldest_exclusive
                    + timedelta(days=1)
                ).isoformat(),
                "max": youngest_inclusive.isoformat(),
            }
        )

    def clean_full_name(self):
        full_name = (
            self.cleaned_data.get("full_name", "") or ""
        ).strip()

        if len(full_name.split()) < 2:
            raise ValidationError(
                "Enter your first and last name."
            )

        return full_name

    def clean_phone_number(self):
        return (
            self.cleaned_data.get("phone_number", "") or ""
        ).strip()

    def clean_gender(self):
        gender = self.cleaned_data.get("gender", "")
        profile_gender = mapped_profile_gender(gender)

        if not profile_gender:
            raise ValidationError(
                "This selection is temporarily unavailable. "
                "Choose another option."
            )

        self._validated_profile_gender = profile_gender
        return gender

    def clean_interested_in(self):
        interested_in = self.cleaned_data.get(
            "interested_in",
            "",
        )
        profile_preference = mapped_profile_preference(
            interested_in
        )

        if not profile_preference:
            raise ValidationError(
                "This selection is temporarily unavailable. "
                "Choose another option."
            )

        self._validated_profile_preference = (
            profile_preference
        )
        return interested_in

    def clean_date_of_birth(self):
        date_of_birth = self.cleaned_data.get(
            "date_of_birth"
        )
        age = age_from_date_of_birth(date_of_birth)

        if age is None or not (
            MINIMUM_LEGAL_AGE
            <= age
            <= MAXIMUM_LEGAL_AGE
        ):
            raise ValidationError(
                "Heartly accounts are available only to "
                "confirmed adults between 18 and 100."
            )

        return date_of_birth

    def signup(self, request, user):
        full_name = self.cleaned_data["full_name"]
        gender = self.cleaned_data["gender"]
        connection_goal = self.cleaned_data[
            "connection_goal"
        ]
        interested_in = self.cleaned_data[
            "interested_in"
        ]
        date_of_birth = self.cleaned_data[
            "date_of_birth"
        ]

        profile_gender = getattr(
            self,
            "_validated_profile_gender",
            None,
        )
        profile_preference = getattr(
            self,
            "_validated_profile_preference",
            None,
        )

        if not profile_gender or not profile_preference:
            raise ValidationError(
                "The selected identity details could not "
                "be synchronized."
            )

        name_parts = full_name.split()

        with transaction.atomic():
            user.full_name = full_name
            user.first_name = (
                name_parts[0] if name_parts else ""
            )
            user.last_name = (
                " ".join(name_parts[1:])
                if len(name_parts) > 1
                else ""
            )
            user.phone_number = self.cleaned_data.get(
                "phone_number",
                "",
            )
            user.gender = gender
            user.interested_in = interested_in
            user.date_of_birth = date_of_birth
            user.save()

            profile, _ = Profile.objects.get_or_create(
                user=user
            )
            display_name_max = Profile._meta.get_field(
                "display_name"
            ).max_length

            profile.display_name = full_name[
                :display_name_max
            ]
            profile.age = age_from_date_of_birth(
                date_of_birth
            )
            profile.gender = profile_gender
            profile.connection_goal = connection_goal
            profile.interested_in = profile_preference
            profile.save(
                update_fields=[
                    "display_name",
                    "age",
                    "gender",
                    "connection_goal",
                    "interested_in",
                    "updated_at",
                ]
            )

        return user
