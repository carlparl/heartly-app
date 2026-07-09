from django.conf import settings
from django.db import models
from django.db.models import Q


class ChatThread(models.Model):
    user_one = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_threads_as_user_one",
    )
    user_two = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_threads_as_user_two",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user_one", "user_two"],
                name="unique_chat_thread_pair",
            )
        ]

    def __str__(self):
        return f"{self.user_one} ↔ {self.user_two}"

    def other_user(self, user):
        return self.user_two if self.user_one_id == user.id else self.user_one

    def has_user(self, user):
        return self.user_one_id == user.id or self.user_two_id == user.id

    @classmethod
    def between(cls, user_a, user_b):
        return cls.objects.filter(
            Q(user_one=user_a, user_two=user_b)
            | Q(user_one=user_b, user_two=user_a)
        ).first()

    @classmethod
    def get_or_create_between(cls, user_a, user_b):
        existing_thread = cls.between(user_a, user_b)

        if existing_thread:
            return existing_thread

        first_user, second_user = sorted([user_a, user_b], key=lambda user: user.id)

        return cls.objects.create(
            user_one=first_user,
            user_two=second_user,
        )


class ChatMessage(models.Model):
    thread = models.ForeignKey(
        ChatThread,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_chat_messages",
    )
    reply_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="replies",
        blank=True,
        null=True,
    )
    text = models.TextField(max_length=1200, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["thread", "created_at"]),
            models.Index(fields=["sender", "created_at"]),
            models.Index(fields=["reply_to"]),
            models.Index(fields=["is_read"]),
        ]

    def __str__(self):
        return f"{self.sender}: {self.text[:40] if self.text else 'media message'}"


class ChatAttachment(models.Model):
    TYPE_IMAGE = "image"
    TYPE_VIDEO = "video"
    TYPE_FILE = "file"
    TYPE_AUDIO = "audio"

    TYPE_CHOICES = [
        (TYPE_IMAGE, "Image"),
        (TYPE_VIDEO, "Video"),
        (TYPE_FILE, "File"),
        (TYPE_AUDIO, "Voice note"),
    ]

    message = models.ForeignKey(
        ChatMessage,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    attachment_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    file = models.FileField(upload_to="chat_attachments/%Y/%m/")
    original_filename = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["attachment_type"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.attachment_type} on message {self.message_id}"


class ChatReport(models.Model):
    REASON_SPAM = "spam"
    REASON_HARASSMENT = "harassment"
    REASON_UNSAFE = "unsafe"
    REASON_FAKE = "fake"
    REASON_OTHER = "other"

    REASON_CHOICES = [
        (REASON_SPAM, "Spam"),
        (REASON_HARASSMENT, "Harassment"),
        (REASON_UNSAFE, "Unsafe content"),
        (REASON_FAKE, "Fake or misleading"),
        (REASON_OTHER, "Other"),
    ]

    thread = models.ForeignKey(
        ChatThread,
        on_delete=models.CASCADE,
        related_name="reports",
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_reports_made",
    )
    reported_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_reports_received",
    )
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reporter} reported {self.reported_user}"


class Call(models.Model):
    TYPE_AUDIO = "audio"
    TYPE_VIDEO = "video"

    TYPE_CHOICES = [
        (TYPE_AUDIO, "Audio"),
        (TYPE_VIDEO, "Video"),
    ]

    STATUS_RINGING = "ringing"
    STATUS_ANSWERED = "answered"
    STATUS_DECLINED = "declined"
    STATUS_ENDED = "ended"
    STATUS_MISSED = "missed"

    STATUS_CHOICES = [
        (STATUS_RINGING, "Ringing"),
        (STATUS_ANSWERED, "Answered"),
        (STATUS_DECLINED, "Declined"),
        (STATUS_ENDED, "Ended"),
        (STATUS_MISSED, "Missed"),
    ]

    thread = models.ForeignKey(
        ChatThread,
        on_delete=models.CASCADE,
        related_name="calls",
    )
    caller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="calls_made",
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="calls_received",
    )
    call_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_RINGING)
    started_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["thread", "started_at"]),
            models.Index(fields=["caller", "started_at"]),
            models.Index(fields=["receiver", "started_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.call_type} call from {self.caller} to {self.receiver}"


class CallSession(models.Model):
    CALL_AUDIO = "audio"
    CALL_VIDEO = "video"

    CALL_TYPE_CHOICES = [
        (CALL_AUDIO, "Audio"),
        (CALL_VIDEO, "Video"),
    ]

    STATUS_RINGING = "ringing"
    STATUS_ACCEPTED = "accepted"
    STATUS_DECLINED = "declined"
    STATUS_ENDED = "ended"
    STATUS_MISSED = "missed"

    STATUS_CHOICES = [
        (STATUS_RINGING, "Ringing"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_DECLINED, "Declined"),
        (STATUS_ENDED, "Ended"),
        (STATUS_MISSED, "Missed"),
    ]

    thread = models.ForeignKey(
        ChatThread,
        on_delete=models.CASCADE,
        related_name="call_sessions",
    )
    caller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="outgoing_calls",
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="incoming_calls",
    )
    call_type = models.CharField(max_length=10, choices=CALL_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RINGING)
    started_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["thread", "started_at"]),
            models.Index(fields=["caller", "started_at"]),
            models.Index(fields=["receiver", "started_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.call_type} call from {self.caller} to {self.receiver}"
