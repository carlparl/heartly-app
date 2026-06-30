from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Max


class ConversationQuerySet(models.QuerySet):
    def for_user(self, user):
        """
        Return conversations where the given user is one of the participants.
        """
        if not user or not user.is_authenticated:
            return self.none()

        return self.filter(Q(user_one=user) | Q(user_two=user))

    def with_last_message_time(self):
        """
        Annotate conversations with the latest message timestamp.
        Useful for ordering chat list pages.
        """
        return self.annotate(last_message_time=Max("messages__created_at"))


class ConversationManager(models.Manager):
    def get_queryset(self):
        return ConversationQuerySet(self.model, using=self._db)

    def for_user(self, user):
        return self.get_queryset().for_user(user)

    def between(self, user_a, user_b):
        """
        Create or return one stable conversation between two users.

        This prevents duplicate pairs like:
        user_a -> user_b
        user_b -> user_a
        """
        if not user_a or not user_b:
            raise ValidationError("Both users are required.")

        if user_a.pk == user_b.pk:
            raise ValidationError("A user cannot start a conversation with themselves.")

        user_one, user_two = sorted([user_a, user_b], key=lambda user: user.pk)

        conversation, created = self.get_or_create(
            user_one=user_one,
            user_two=user_two,
        )

        return conversation


class Conversation(models.Model):
    user_one = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_conversations_as_user_one",
    )
    user_two = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_conversations_as_user_two",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ConversationManager()

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user_one", "user_two"],
                name="unique_conversation_between_two_users",
            ),
            models.CheckConstraint(
                condition=~Q(user_one=models.F("user_two")),
                name="conversation_users_cannot_be_same",
            ),
        ]
        indexes = [
            models.Index(fields=["user_one", "updated_at"]),
            models.Index(fields=["user_two", "updated_at"]),
            models.Index(fields=["updated_at"]),
        ]

    def clean(self):
        if self.user_one_id and self.user_two_id:
            if self.user_one_id == self.user_two_id:
                raise ValidationError("A user cannot have a conversation with themselves.")

    def save(self, *args, **kwargs):
        """
        Keep user ordering stable before saving.

        Lower user ID is always user_one.
        Higher user ID is always user_two.
        """
        if self.user_one_id and self.user_two_id:
            if self.user_one_id == self.user_two_id:
                raise ValidationError("A user cannot have a conversation with themselves.")

            if self.user_one_id > self.user_two_id:
                self.user_one_id, self.user_two_id = self.user_two_id, self.user_one_id

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Conversation #{self.pk}: {self.user_one} ↔ {self.user_two}"

    def has_participant(self, user):
        return user == self.user_one or user == self.user_two

    def get_other_user(self, current_user):
        if current_user == self.user_one:
            return self.user_two

        if current_user == self.user_two:
            return self.user_one

        raise ValidationError("User is not part of this conversation.")

    def get_last_message(self):
        return (
            self.messages
            .select_related("sender")
            .order_by("-created_at")
            .first()
        )

    def unread_count_for(self, user):
        """
        Count unread messages sent by the other user.
        """
        return (
            self.messages
            .filter(is_read=False)
            .exclude(sender=user)
            .count()
        )

    def mark_read_for(self, user):
        """
        Mark all messages from the other user as read.
        """
        return (
            self.messages
            .filter(is_read=False)
            .exclude(sender=user)
            .update(is_read=True)
        )


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_messages_sent",
    )
    content = models.TextField(max_length=2000)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
            models.Index(fields=["sender", "created_at"]),
            models.Index(fields=["conversation", "is_read"]),
        ]

    def clean(self):
        if not self.content or not self.content.strip():
            raise ValidationError("Message content cannot be empty.")

        if self.sender_id and self.conversation_id:
            is_participant = (
                self.conversation.user_one_id == self.sender_id
                or self.conversation.user_two_id == self.sender_id
            )

            if not is_participant:
                raise ValidationError("Sender must be part of the conversation.")

    def save(self, *args, **kwargs):
        self.content = self.content.strip()

        self.full_clean()

        super().save(*args, **kwargs)

        Conversation.objects.filter(id=self.conversation_id).update(
            updated_at=self.created_at
        )

    def __str__(self):
        return f"Message #{self.pk} from {self.sender}"

    @property
    def short_content(self):
        if len(self.content) <= 60:
            return self.content

        return f"{self.content[:60]}..."