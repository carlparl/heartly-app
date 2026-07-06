from django import forms
from django.contrib.auth import get_user_model
from allauth.account.forms import SignupForm


User = get_user_model()


class CustomSignupForm(SignupForm):
    """
    Required because settings.py/allauth is pointing to:
    accounts.forms.CustomSignupForm

    Keep this class even if it does nothing extra yet.
    """

    def save(self, request):
        user = super().save(request)
        return user


class AccountSettingsForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "email"]

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