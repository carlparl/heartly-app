from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


class Interest(models.Model):
    name = models.CharField(max_length=80, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    display_name = models.CharField(max_length=120, blank=True)
    age = models.PositiveIntegerField(blank=True, null=True)
    location = models.CharField(max_length=120, blank=True)
    bio = models.TextField(blank=True)

    profile_picture = models.ImageField(
        upload_to="profiles/photos/",
        blank=True,
        null=True,
    )

    interests = models.ManyToManyField(
        Interest,
        blank=True,
        related_name="profiles",
    )

    email_verified = models.BooleanField(default=False)

    profile_visible = models.BooleanField(default=True)
    show_online_status = models.BooleanField(default=False)
    allow_message_requests = models.BooleanField(default=True)
    safety_filters_enabled = models.BooleanField(default=True)

    hidden_by_moderation = models.BooleanField(default=False)
    moderation_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name

    @property
    def name(self):
        return self.display_name or self.user.get_full_name() or self.user.username


class UserBlock(models.Model):
    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocks_made",
    )

    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocks_received",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("blocker", "blocked")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.blocker} blocked {self.blocked}"

    @staticmethod
    def is_blocked_between(user_one, user_two):
        return UserBlock.objects.filter(
            Q(blocker=user_one, blocked=user_two)
            | Q(blocker=user_two, blocked=user_one)
        ).exists()


class ProfileReport(models.Model):
    REASON_FAKE = "fake"
    REASON_HARASSMENT = "harassment"
    REASON_INAPPROPRIATE = "inappropriate"
    REASON_SPAM = "spam"
    REASON_UNSAFE = "unsafe"
    REASON_OTHER = "other"

    REASON_CHOICES = [
        (REASON_FAKE, "Fake profile or scam"),
        (REASON_HARASSMENT, "Harassment or bullying"),
        (REASON_INAPPROPRIATE, "Inappropriate profile"),
        (REASON_SPAM, "Spam or misleading"),
        (REASON_UNSAFE, "Unsafe behavior"),
        (REASON_OTHER, "Other"),
    ]

    STATUS_PENDING = "pending"
    STATUS_REVIEWED = "reviewed"
    STATUS_ACTIONED = "actioned"
    STATUS_DISMISSED = "dismissed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_REVIEWED, "Reviewed"),
        (STATUS_ACTIONED, "Action taken"),
        (STATUS_DISMISSED, "Dismissed"),
    ]

    reported_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile_reports_received",
    )

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile_reports_submitted",
    )

    reason = models.CharField(
        max_length=40,
        choices=REASON_CHOICES,
        default=REASON_OTHER,
    )

    details = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )

    reviewed = models.BooleanField(default=False)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reviewed_profile_reports",
    )

    reviewed_at = models.DateTimeField(blank=True, null=True)
    moderator_note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("reported_user", "reporter")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reporter} reported {self.reported_user}"

    def mark_reviewed(self, moderator=None, note=""):
        self.reviewed = True
        self.status = self.STATUS_REVIEWED
        self.reviewed_by = moderator
        self.reviewed_at = timezone.now()
        self.moderator_note = note
        self.save(
            update_fields=[
                "reviewed",
                "status",
                "reviewed_by",
                "reviewed_at",
                "moderator_note",
            ]
        )

    def mark_actioned(self, moderator=None, note=""):
        self.reviewed = True
        self.status = self.STATUS_ACTIONED
        self.reviewed_by = moderator
        self.reviewed_at = timezone.now()
        self.moderator_note = note
        self.save(
            update_fields=[
                "reviewed",
                "status",
                "reviewed_by",
                "reviewed_at",
                "moderator_note",
            ]
        )

    def dismiss(self, moderator=None, note=""):
        self.reviewed = True
        self.status = self.STATUS_DISMISSED
        self.reviewed_by = moderator
        self.reviewed_at = timezone.now()
        self.moderator_note = note
        self.save(
            update_fields=[
                "reviewed",
                "status",
                "reviewed_by",
                "reviewed_at",
                "moderator_note",
            ]
        )


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    profile, created_profile = Profile.objects.get_or_create(user=instance)

    if created_profile and not profile.display_name:
        profile.display_name = instance.get_full_name() or instance.username
        profile.save()