from django.conf import settings
from django.db import models


class MatchAction(models.Model):
    LIKE = "like"
    PASS = "pass"

    ACTION_CHOICES = [
        (LIKE, "Like"),
        (PASS, "Pass"),
    ]

    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_match_actions",
    )

    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_match_actions",
    )

    action = models.CharField(
        max_length=10,
        choices=ACTION_CHOICES,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["from_user", "to_user"],
                name="unique_match_action",
            )
        ]

    def __str__(self):
        return f"{self.from_user} {self.action} {self.to_user}"


class MutualMatch(models.Model):
    user_one = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="matches_as_user_one",
    )

    user_two = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="matches_as_user_two",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user_one", "user_two"],
                name="unique_mutual_match",
            )
        ]

    def __str__(self):
        return f"{self.user_one} matched with {self.user_two}"

    @classmethod
    def create_safe(cls, user_a, user_b):
        if user_a == user_b:
            return None

        first, second = sorted(
            [user_a, user_b],
            key=lambda user: user.id,
        )

        match, created = cls.objects.get_or_create(
            user_one=first,
            user_two=second,
        )

        return match