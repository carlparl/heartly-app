from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Interest(models.Model):
    name = models.CharField(max_length=80, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Profile(models.Model):
    GENDER_WOMAN = "woman"
    GENDER_MAN = "man"
    GENDER_NON_BINARY = "non_binary"
    GENDER_OTHER = "other"

    GENDER_CHOICES = [
        (GENDER_WOMAN, "Woman"),
        (GENDER_MAN, "Man"),
        (GENDER_NON_BINARY, "Non-binary"),
        (GENDER_OTHER, "Other"),
    ]

    INTERESTED_IN_WOMEN = "women"
    INTERESTED_IN_MEN = "men"
    INTERESTED_IN_EVERYONE = "everyone"

    INTERESTED_IN_CHOICES = [
        (INTERESTED_IN_WOMEN, "Women"),
        (INTERESTED_IN_MEN, "Men"),
        (INTERESTED_IN_EVERYONE, "Everyone"),
    ]

    CONNECTION_DATING = "dating"
    CONNECTION_FRIENDSHIP = "friendship"
    CONNECTION_BOTH = "both"

    CONNECTION_GOAL_CHOICES = [
        (CONNECTION_DATING, "Dating"),
        (CONNECTION_FRIENDSHIP, "Friendship"),
        (CONNECTION_BOTH, "Dating and friendship"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    display_name = models.CharField(max_length=120, blank=True)
    age = models.PositiveIntegerField(blank=True, null=True)
    location = models.CharField(max_length=120, blank=True)
    bio = models.TextField(blank=True)
    gender = models.CharField(
        max_length=20,
        choices=GENDER_CHOICES,
        blank=True,
    )
    interested_in = models.CharField(
        max_length=20,
        choices=INTERESTED_IN_CHOICES,
        blank=True,
    )
    connection_goal = models.CharField(
        max_length=20,
        choices=CONNECTION_GOAL_CHOICES,
        default=CONNECTION_DATING,
    )

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
        indexes = [
            models.Index(
                fields=[
                    "profile_visible",
                    "hidden_by_moderation",
                    "gender",
                    "interested_in",
                    "connection_goal",
                    "-updated_at",
                ],
                name="profiles_discovery_idx",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def name(self):
        return self.display_name or self.user.get_full_name() or self.user.username

    @property
    def primary_photo(self):
        prefetched = getattr(self, "_prefetched_objects_cache", {}).get("photos")
        if prefetched is not None:
            return next(iter(prefetched), None)
        return self.photos.order_by("position", "id").first()

    @property
    def primary_photo_url(self):
        photo = self.primary_photo
        if photo and photo.image:
            try:
                return photo.image.url
            except Exception:
                pass

        if self.profile_picture:
            try:
                return self.profile_picture.url
            except Exception:
                pass

        return ""


class ProfilePhoto(models.Model):
    MAX_PHOTOS = 4

    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="photos",
    )
    image = models.ImageField(upload_to="profiles/photos/")
    position = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "position"],
                name="unique_profile_photo_position",
            ),
            models.CheckConstraint(
                condition=Q(position__gte=1, position__lte=4),
                name="profile_photo_position_1_to_4",
            ),
        ]

    def clean(self):
        super().clean()
        if not 1 <= self.position <= self.MAX_PHOTOS:
            raise ValidationError({"position": "Profile photo position must be between 1 and 4."})

    def __str__(self):
        return f"{self.profile.name} photo {self.position}"


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


class ModerationAction(models.Model):
    ACTION_REPORT_REVIEWED = "report_reviewed"
    ACTION_REPORT_ACTIONED = "report_actioned"
    ACTION_REPORT_DISMISSED = "report_dismissed"
    ACTION_PROFILE_HIDDEN = "profile_hidden"
    ACTION_PROFILE_RESTORED = "profile_restored"
    ACTION_POST_HIDDEN = "post_hidden"
    ACTION_POST_RESTORED = "post_restored"
    ACTION_ACCOUNT_SUSPENDED = "account_suspended"
    ACTION_ACCOUNT_BANNED = "account_banned"
    ACTION_ACCOUNT_RESTORED = "account_restored"

    ACTION_CHOICES = [
        (ACTION_REPORT_REVIEWED, "Report reviewed"),
        (ACTION_REPORT_ACTIONED, "Report actioned"),
        (ACTION_REPORT_DISMISSED, "Report dismissed"),
        (ACTION_PROFILE_HIDDEN, "Profile hidden"),
        (ACTION_PROFILE_RESTORED, "Profile restored"),
        (ACTION_POST_HIDDEN, "Post hidden"),
        (ACTION_POST_RESTORED, "Post restored"),
        (ACTION_ACCOUNT_SUSPENDED, "Account suspended"),
        (ACTION_ACCOUNT_BANNED, "Account banned"),
        (ACTION_ACCOUNT_RESTORED, "Account restored"),
    ]

    SOURCE_PROFILE = "profile"
    SOURCE_PROFILE_REPORT = "profile_report"
    SOURCE_POST = "post"
    SOURCE_POST_REPORT = "post_report"
    SOURCE_CHAT_REPORT = "chat_report"
    SOURCE_ACCOUNT = "account"

    SOURCE_CHOICES = [
        (SOURCE_PROFILE, "Profile"),
        (SOURCE_PROFILE_REPORT, "Profile report"),
        (SOURCE_POST, "Post"),
        (SOURCE_POST_REPORT, "Post report"),
        (SOURCE_CHAT_REPORT, "Chat report"),
        (SOURCE_ACCOUNT, "Account"),
    ]

    moderator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="moderation_actions_performed",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="moderation_actions_received",
    )
    action = models.CharField(
        max_length=40,
        choices=ACTION_CHOICES,
    )
    source_type = models.CharField(
        max_length=40,
        choices=SOURCE_CHOICES,
    )
    source_object_id = models.PositiveBigIntegerField(
        blank=True,
        null=True,
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["-created_at"],
                name="profiles_mod_created_idx",
            ),
            models.Index(
                fields=["target_user", "-created_at"],
                name="profiles_mod_target_idx",
            ),
            models.Index(
                fields=["action", "-created_at"],
                name="profiles_mod_action_idx",
            ),
        ]

    def __str__(self):
        return f"{self.get_action_display()} by {self.moderator or 'system'}"


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
    evidence_snapshot = models.JSONField(
        default=dict,
        blank=True,
    )

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
