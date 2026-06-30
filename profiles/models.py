from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.display_name or self.user.get_full_name() or self.user.username

    @property
    def name(self):
        return self.display_name or self.user.get_full_name() or self.user.username


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    profile, _ = Profile.objects.get_or_create(user=instance)

    if created and not profile.display_name:
        profile.display_name = instance.get_full_name() or instance.username
        profile.save()