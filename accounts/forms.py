from datetime import date

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import CustomUser


USER_TO_PROFILE_GENDER = {
    "male": "man",
    "female": "woman",
    "non_binary": "non_binary",
    "prefer_not_to_say": "other",
}

USER_TO_PROFILE_INTERESTED_IN = {
    "male": "men",
    "female": "women",
    "both": "everyone",
    "friends": "everyone",
}


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
        choices=[("", "Select your gender")] + CustomUser.GENDER_CHOICES,
        required=True,
        label="Gender",
        widget=forms.Select(
            attrs={
                "class": "heartly-input",
            }
        ),
    )

    interested_in = forms.ChoiceField(
        choices=[("", "Who are you interested in?")] + CustomUser.INTERESTED_IN_CHOICES,
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
            attrs={
                "type": "date",
                "class": "heartly-input",
            }
        ),
    )

    def clean_full_name(self):
        full_name = self.cleaned_data.get("full_name", "").strip()

        if len(full_name.split()) < 2:
            raise ValidationError("Enter your first and last name.")

        return full_name

    def clean_phone_number(self):
        return self.cleaned_data.get("phone_number", "").strip()

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get("date_of_birth")

        if not dob:
            return dob

        today = date.today()

        if dob >= today:
            raise ValidationError("Enter a valid date of birth.")

        age = (
            today.year
            - dob.year
            - ((today.month, today.day) < (dob.month, dob.day))
        )

        if age < 18:
            raise ValidationError(
                "You must be at least 18 years old to create a Heartly account."
            )

        if age > 100:
            raise ValidationError("Enter a valid date of birth.")

        return dob

    def signup(self, request, user):
        """
        Save Heartly signup fields and initialize the linked Profile.

        The project still contains temporary duplicate identity fields on
        CustomUser and Profile. During the rebuild, both copies are kept in
        sync so existing views continue to work while we prepare a safe data
        migration to one permanent source of truth.
        """
        from profiles.models import Profile

        with transaction.atomic():
            user.full_name = self.cleaned_data["full_name"]
            user.phone_number = self.cleaned_data.get("phone_number", "")
            user.gender = self.cleaned_data["gender"]
            user.interested_in = self.cleaned_data["interested_in"]
            user.date_of_birth = self.cleaned_data["date_of_birth"]
            user.save()

            profile, _ = Profile.objects.get_or_create(user=user)
            display_name_max = Profile._meta.get_field("display_name").max_length

            profile.display_name = user.full_name[:display_name_max]
            profile.age = user.age
            profile.gender = USER_TO_PROFILE_GENDER.get(user.gender, "")
            profile.interested_in = USER_TO_PROFILE_INTERESTED_IN.get(
                user.interested_in,
                "",
            )
            profile.save(
                update_fields=[
                    "display_name",
                    "age",
                    "gender",
                    "interested_in",
                    "updated_at",
                ]
            )

        return user
