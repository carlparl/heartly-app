from datetime import date

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.text import slugify


class CustomUser(AbstractUser):
    GENDER_CHOICES = [
        ("male", "Male"),
        ("female", "Female"),
        ("non_binary", "Non-binary"),
        ("prefer_not_to_say", "Prefer not to say"),
    ]

    INTERESTED_IN_CHOICES = [
        ("male", "Men"),
        ("female", "Women"),
        ("both", "Everyone"),
        ("friends", "Friends first"),
    ]

    email = models.EmailField(
        unique=True,
        help_text="User email address. Used for login.",
    )

    full_name = models.CharField(
        max_length=150,
        blank=True,
    )

    phone_number = models.CharField(
        max_length=20,
        blank=True,
    )

    gender = models.CharField(
        max_length=30,
        choices=GENDER_CHOICES,
        blank=True,
    )

    interested_in = models.CharField(
        max_length=30,
        choices=INTERESTED_IN_CHOICES,
        blank=True,
    )

    date_of_birth = models.DateField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def save(self, *args, **kwargs):
        """
        Keeps username safe even when the app uses email login.
        Allauth may not ask for username, but Django's AbstractUser still has it.
        """
        if not self.username:
            base_username = self.email.split("@")[0] if self.email else "heartly-user"
            base_username = slugify(base_username) or "heartly-user"

            username = base_username
            counter = 1

            while CustomUser.objects.filter(username=username).exclude(pk=self.pk).exists():
                username = f"{base_username}-{counter}"
                counter += 1

            self.username = username

        if self.full_name and not self.first_name:
            name_parts = self.full_name.strip().split()
            self.first_name = name_parts[0]
            self.last_name = " ".join(name_parts[1:])

        super().save(*args, **kwargs)

    @property
    def age(self):
        if not self.date_of_birth:
            return None

        today = date.today()

        return (
            today.year
            - self.date_of_birth.year
            - (
                (today.month, today.day)
                < (self.date_of_birth.month, self.date_of_birth.day)
            )
        )

    def get_display_name(self):
        if self.full_name:
            return self.full_name

        full_name = self.get_full_name()

        if full_name:
            return full_name

        return self.email or self.username

    def __str__(self):
        return self.get_display_name()