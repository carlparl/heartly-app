from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from profiles.models import Profile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_user_profile(
    sender,
    instance,
    created,
    raw=False,
    **kwargs,
):
    # Prevent duplicate profiles during fixture imports.
    if raw:
        return

    Profile.objects.get_or_create(user=instance)