from django.db import models
from django.conf import settings


class HeartlyMessage(models.Model):
    ROLE_CHOICES = (
        ("user", "User"),
        ("ai", "AI"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="heartly_ai_messages",
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user.email or self.user.username} - {self.role}: {self.text[:40]}"