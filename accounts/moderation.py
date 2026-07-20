from django.contrib.auth import get_user_model


def account_can_access(user):
    if not user or not user.is_authenticated:
        return False
    return (
        user.active_moderation_status()
        == user.MODERATION_CLEAR
    )


def account_id_can_access(user_id):
    User = get_user_model()
    user = (
        User.objects.only(
            "id",
            "is_staff",
            "is_superuser",
            "moderation_status",
            "moderation_expires_at",
        )
        .filter(pk=user_id)
        .first()
    )
    return account_can_access(user)
