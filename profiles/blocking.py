from .models import Profile, UserBlock


def model_has_field(model, field_name):
    return any(field.name == field_name for field in model._meta.fields)


def hidden_user_ids_for(user):
    if not user.is_authenticated:
        return set()

    users_i_blocked = UserBlock.objects.filter(
        blocker=user,
    ).values_list("blocked_id", flat=True)

    users_who_blocked_me = UserBlock.objects.filter(
        blocked=user,
    ).values_list("blocker_id", flat=True)

    hidden_ids = set(users_i_blocked) | set(users_who_blocked_me)

    if model_has_field(Profile, "hidden_by_moderation"):
        moderated_ids = Profile.objects.filter(
            hidden_by_moderation=True,
        ).exclude(
            user=user,
        ).values_list("user_id", flat=True)

        hidden_ids |= set(moderated_ids)

    if model_has_field(Profile, "profile_visible"):
        private_ids = Profile.objects.filter(
            profile_visible=False,
        ).exclude(
            user=user,
        ).values_list("user_id", flat=True)

        hidden_ids |= set(private_ids)

    return hidden_ids


def block_exists_between(user, other_user):
    if not user.is_authenticated or not other_user:
        return False

    return (
        UserBlock.objects.filter(blocker=user, blocked=other_user).exists()
        or UserBlock.objects.filter(blocker=other_user, blocked=user).exists()
    )


def user_is_hidden_for(viewer, target_user):
    if not viewer.is_authenticated or not target_user:
        return True

    if viewer == target_user:
        return False

    return target_user.id in hidden_user_ids_for(viewer)