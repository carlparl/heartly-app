from datetime import date

from django import forms
from django.contrib.auth import get_user_model


User = get_user_model()


class CustomSignupForm(forms.Form):
    full_name = forms.CharField(
        max_length=150,
        required=True,
        label="Full name",
        widget=forms.TextInput(attrs={
            "placeholder": "Your full name",
            "autocomplete": "name",
        }),
    )

    phone_number = forms.CharField(
        max_length=20,
        required=False,
        label="Phone number",
        widget=forms.TextInput(attrs={
            "placeholder": "Optional phone number",
            "autocomplete": "tel",
        }),
    )

    gender = forms.ChoiceField(
        required=True,
        label="Gender",
        choices=[("", "Choose your gender")] + list(User.GENDER_CHOICES),
        widget=forms.Select(),
    )

    interested_in = forms.ChoiceField(
        required=True,
        label="What do you need from Heartly?",
        choices=[("", "Choose one")] + list(User.INTERESTED_IN_CHOICES),
        widget=forms.Select(),
    )

    date_of_birth = forms.DateField(
        required=True,
        label="Date of birth",
        widget=forms.DateInput(attrs={
            "type": "date",
            "autocomplete": "bday",
        }),
    )

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

        if age < 13:
            raise forms.ValidationError("You must be at least 13 to use Heartly.")

        if age > 120:
            raise forms.ValidationError("Enter a valid date of birth.")

        return dob

    def signup(self, request, user):
        user.full_name = self.cleaned_data["full_name"]
        user.phone_number = self.cleaned_data.get("phone_number", "")
        user.gender = self.cleaned_data["gender"]
        user.interested_in = self.cleaned_data["interested_in"]
        user.date_of_birth = self.cleaned_data["date_of_birth"]
        user.save()


class AccountSettingsForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "full_name",
            "phone_number",
            "gender",
            "interested_in",
            "date_of_birth",
        ]

        widgets = {
            "username": forms.TextInput(attrs={
                "class": "heartly-input",
                "placeholder": "Username",
                "autocomplete": "username",
            }),
            "email": forms.EmailInput(attrs={
                "class": "heartly-input",
                "placeholder": "Email address",
                "autocomplete": "email",
            }),
            "full_name": forms.TextInput(attrs={
                "class": "heartly-input",
                "placeholder": "Full name",
                "autocomplete": "name",
            }),
            "phone_number": forms.TextInput(attrs={
                "class": "heartly-input",
                "placeholder": "Phone number",
                "autocomplete": "tel",
            }),
            "gender": forms.Select(attrs={
                "class": "heartly-input",
            }),
            "interested_in": forms.Select(attrs={
                "class": "heartly-input",
            }),
            "date_of_birth": forms.DateInput(attrs={
                "class": "heartly-input",
                "type": "date",
                "autocomplete": "bday",
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()

        if not username:
            raise forms.ValidationError("Username is required.")

        query = User.objects.filter(username__iexact=username)

        if self.user:
            query = query.exclude(pk=self.user.pk)

        if query.exists():
            raise forms.ValidationError("This username is already taken.")

        return username

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()

        if not email:
            raise forms.ValidationError("Email is required.")

        query = User.objects.filter(email__iexact=email)

        if self.user:
            query = query.exclude(pk=self.user.pk)

        if query.exists():
            raise forms.ValidationError("This email is already used by another account.")

        return email

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

        if age < 13:
            raise forms.ValidationError("You must be at least 13 to use Heartly.")

        if age > 120:
            raise forms.ValidationError("Enter a valid date of birth.")

        return dob


class VerifyEmailCodeForm(forms.Form):
    code = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            "class": "heartly-input verification-code-input",
            "placeholder": "Enter 6-digit code",
            "inputmode": "numeric",
            "autocomplete": "one-time-code",
        }),
    )

    def clean_code(self):
        code = self.cleaned_data["code"].strip()

        if not code.isdigit():
            raise forms.ValidationError("Enter digits only.")

        return code