from allauth.account.models import EmailAddress
from django.conf import settings
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from profiles.models import Profile

from .models import EmailVerificationCode


def normalized_email(value):
    return (value or "").strip().casefold()


@receiver(pre_save, sender=settings.AUTH_USER_MODEL)
def capture_previous_user_email(sender, instance, raw=False, **kwargs):
    if raw or not instance.pk:
        return

    instance._heartly_previous_email = (
        sender.objects
        .filter(pk=instance.pk)
        .values_list("email", flat=True)
        .first()
    )


def secure_changed_email(user, previous_email):
    current_email = (user.email or "").strip()

    if normalized_email(previous_email) == normalized_email(current_email):
        return

    now = timezone.now()

    EmailVerificationCode.objects.filter(
        user=user,
        used_at__isnull=True,
    ).update(used_at=now)

    EmailAddress.objects.filter(
        user=user,
        primary=True,
    ).update(primary=False)

    if current_email:
        email_address = (
            EmailAddress.objects
            .filter(user=user, email__iexact=current_email)
            .first()
        )

        if email_address is None:
            email_address = EmailAddress(
                user=user,
                email=current_email,
            )

        email_address.email = current_email
        email_address.primary = True
        email_address.verified = False
        email_address.save()

    Profile.objects.filter(user=user).update(
        email_verified=False
    )


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

    if not created:
        previous_email = getattr(
            instance,
            "_heartly_previous_email",
            instance.email,
        )
        secure_changed_email(instance, previous_email)


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
def sync_email_address_save(sender, instance, raw=False, **kwargs):
    if raw:
        return
    sync_profile_email_verified(instance.user)


@receiver(post_delete, sender=EmailAddress)
def sync_email_address_delete(sender, instance, **kwargs):
    sync_profile_email_verified(instance.user)
