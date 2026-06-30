from django import forms
from .models import Interest, Profile


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            "display_name",
            "age",
            "location",
            "bio",
            "profile_picture",
        ]

        widgets = {
            "display_name": forms.TextInput(attrs={
                "class": "heartly-input",
                "placeholder": "Your display name",
            }),
            "age": forms.NumberInput(attrs={
                "class": "heartly-input",
                "placeholder": "Age",
                "min": "13",
                "max": "120",
            }),
            "location": forms.TextInput(attrs={
                "class": "heartly-input",
                "placeholder": "City, country",
            }),
            "bio": forms.Textarea(attrs={
                "class": "heartly-textarea",
                "placeholder": "Write a short bio...",
                "rows": 4,
            }),
            "profile_picture": forms.ClearableFileInput(attrs={
                "class": "heartly-input",
            }),
        }


class InterestForm(forms.ModelForm):
    interests = forms.ModelMultipleChoiceField(
        queryset=Interest.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    class Meta:
        model = Profile
        fields = ["interests"]