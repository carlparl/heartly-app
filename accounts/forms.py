from datetime import date

from allauth.account.forms import SignupForm
from django import forms


GENDER_CHOICES = [
    ("", "Choose your gender"),
    ("male", "Male"),
    ("female", "Female"),
    ("non_binary", "Non-binary"),
    ("prefer_not_to_say", "Prefer not to say"),
]

INTERESTED_IN_CHOICES = [
    ("", "Choose who you are interested in"),
    ("male", "Men"),
    ("female", "Women"),
    ("both", "Everyone"),
    ("friends", "Friends first"),
]


INPUT_CLASS = (
    "w-full px-4 py-3.5 border border-gray-300 rounded-2xl "
    "focus:outline-none focus:border-[#ec4899] focus:ring-2 "
    "focus:ring-pink-200 bg-white text-gray-900"
)


class CustomSignupForm(SignupForm):
    full_name = forms.CharField(
        max_length=150,
        required=True,
        label="Full name",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Enter your full name",
                "class": INPUT_CLASS,
                "autocomplete": "name",
            }
        ),
    )

    phone_number = forms.CharField(
        max_length=20,
        required=False,
        label="Phone number",
        widget=forms.TextInput(
            attrs={
                "placeholder": "+256 700 000000",
                "class": INPUT_CLASS,
                "autocomplete": "tel",
            }
        ),
    )

    gender = forms.ChoiceField(
        choices=GENDER_CHOICES,
        required=True,
        label="Gender",
        widget=forms.Select(
            attrs={
                "class": INPUT_CLASS,
            }
        ),
    )

    interested_in = forms.ChoiceField(
        choices=INTERESTED_IN_CHOICES,
        required=True,
        label="Interested in",
        widget=forms.Select(
            attrs={
                "class": INPUT_CLASS,
            }
        ),
    )

    date_of_birth = forms.DateField(
        required=True,
        label="Date of birth",
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": INPUT_CLASS,
                "autocomplete": "bday",
            }
        ),
    )

    def clean_full_name(self):
        full_name = self.cleaned_data.get("full_name", "").strip()

        if len(full_name.split()) < 2:
            raise forms.ValidationError("Please enter both your first and last name.")

        return full_name

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get("date_of_birth")

        if not dob:
            return dob

        today = date.today()

        age = (
            today.year
            - dob.year
            - ((today.month, today.day) < (dob.month, dob.day))
        )

        if dob > today:
            raise forms.ValidationError("Date of birth cannot be in the future.")

        if age < 18:
            raise forms.ValidationError(
                "You must be at least 18 years old to create a Heartly dating account."
            )

        return dob

    def save(self, request):
        user = super().save(request)

        full_name = self.cleaned_data.get("full_name", "").strip()
        name_parts = full_name.split()

        user.first_name = name_parts[0]
        user.last_name = " ".join(name_parts[1:])

        if hasattr(user, "full_name"):
            user.full_name = full_name

        if hasattr(user, "phone_number"):
            user.phone_number = self.cleaned_data.get("phone_number", "")

        if hasattr(user, "gender"):
            user.gender = self.cleaned_data.get("gender", "")

        if hasattr(user, "interested_in"):
            user.interested_in = self.cleaned_data.get("interested_in", "")

        if hasattr(user, "date_of_birth"):
            user.date_of_birth = self.cleaned_data.get("date_of_birth")

        user.save()
        return user