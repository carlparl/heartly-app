from datetime import date, timedelta
import secrets

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class CustomUser(AbstractUser):
    MODERATION_CLEAR = "clear"
    MODERATION_SUSPENDED = "suspended"
    MODERATION_BANNED = "banned"

    MODERATION_STATUS_CHOICES = [
        (MODERATION_CLEAR, "No account restriction"),
        (MODERATION_SUSPENDED, "Suspended"),
        (MODERATION_BANNED, "Banned"),
    ]

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
        db_index=True,
    )

    moderation_status = models.CharField(
        max_length=20,
        choices=MODERATION_STATUS_CHOICES,
        default=MODERATION_CLEAR,
        db_index=True,
    )
    moderation_reason = models.TextField(blank=True)
    moderation_expires_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    moderation_updated_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    moderation_updated_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def save(self, *args, **kwargs):
        """
        Keep username valid even when the app uses email-first signup.
        AbstractUser still requires a username value internally.
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

    def active_moderation_status(self, at=None):
        """Return the restriction currently blocking this account."""
        if self.is_staff or self.is_superuser:
            return self.MODERATION_CLEAR

        if self.moderation_status == self.MODERATION_BANNED:
            return self.MODERATION_BANNED

        if self.moderation_status != self.MODERATION_SUSPENDED:
            return self.MODERATION_CLEAR

        at = at or timezone.now()
        if (
            self.moderation_expires_at
            and self.moderation_expires_at <= at
        ):
            return self.MODERATION_CLEAR

        return self.MODERATION_SUSPENDED

    def __str__(self):
        return self.get_display_name()


class EmailVerificationCode(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_verification_codes",
    )

    email = models.EmailField()
    code_hash = models.CharField(max_length=128)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    used_at = models.DateTimeField(blank=True, null=True)
    attempts = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.email}"

    @classmethod
    def generate_code(cls):
        return f"{secrets.randbelow(1_000_000):06d}"

    @classmethod
    def create_for_user(cls, user):
        raw_code = cls.generate_code()

        cls.objects.filter(
            user=user,
            email=user.email,
            used_at__isnull=True,
        ).update(used_at=timezone.now())

        verification = cls.objects.create(
            user=user,
            email=user.email,
            code_hash=make_password(raw_code),
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        return verification, raw_code

    def is_expired(self):
        return timezone.now() > self.expires_at

    def can_attempt(self):
        return self.attempts < 5 and not self.used_at and not self.is_expired()

    def check_code(self, raw_code):
        if not self.can_attempt():
            return False

        self.attempts += 1
        self.save(update_fields=["attempts"])

        return check_password(raw_code, self.code_hash)

    def mark_used(self):
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])
