from allauth.account.models import EmailAddress
from django.conf import settings
from django.db.models.signals import post_delete, post_save
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
    if raw:
        return
    Profile.objects.get_or_create(user=instance)


def sync_profile_email_verified(user):
    if not user or not user.pk:
        return

    email = (user.email or "").strip()
    verified = bool(
        email
        and EmailAddress.objects.filter(
            user=user,
            email__iexact=email,
            verified=True,
        ).exists()
    )

    Profile.objects.filter(user=user).update(
        email_verified=verified
    )


@receiver(post_save, sender=EmailAddress)
def sync_email_address_save(
    sender,
    instance,
    raw=False,
    **kwargs,
):
    if raw:
        return
    sync_profile_email_verified(instance.user)


@receiver(post_delete, sender=EmailAddress)
def sync_email_address_delete(
    sender,
    instance,
    **kwargs,
):
    sync_profile_email_verified(instance.user)
