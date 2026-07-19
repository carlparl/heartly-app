from allauth.account.models import EmailAddress


def current_email_is_verified(user):
    """Return whether the user's current email is authoritatively verified."""
    email = (getattr(user, "email", "") or "").strip()
    if not email:
        return False

    prefetched = getattr(
        user,
        "_prefetched_objects_cache",
        {},
    ).get("emailaddress_set")

    if prefetched is not None:
        normalized_email = email.casefold()
        return any(
            address.verified
            and (address.email or "").strip().casefold()
            == normalized_email
            for address in prefetched
        )

    return EmailAddress.objects.filter(
        user_id=user.pk,
        email__iexact=email,
        verified=True,
    ).exists()
