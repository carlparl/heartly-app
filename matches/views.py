import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from profiles.identity import (
    identity_issue_messages,
    identity_repair_issues,
    legal_birth_date_bounds,
)
from profiles.models import Profile

from notifications.activity import (
    notify_mutual_match,
    notify_profile_like,
)

from .models import MatchAction, MutualMatch


logger = logging.getLogger(__name__)


try:
    from profiles.blocking import (
        block_exists_between,
        hidden_user_ids_for,
    )
except Exception:
    hidden_user_ids_for = None
    block_exists_between = None


try:
    from notifications.models import Notification
except Exception:
    Notification = None


User = get_user_model()


PROFILE_GENDER_TO_AUDIENCE = {
    Profile.GENDER_WOMAN: Profile.INTERESTED_IN_WOMEN,
    Profile.GENDER_MAN: Profile.INTERESTED_IN_MEN,
}


def model_has_field(model, field_name):
    return any(
        field.name == field_name
        for field in model._meta.fields
    )


def is_ajax_request(request):
    return (
        request.headers.get("X-Requested-With")
        == "XMLHttpRequest"
    )


def build_profile_search_query(search_query):
    search_filter = (
        Q(user__username__icontains=search_query)
        | Q(user__first_name__icontains=search_query)
        | Q(user__last_name__icontains=search_query)
        | Q(display_name__icontains=search_query)
        | Q(bio__icontains=search_query)
    )

    return search_filter


def get_profile(user):
    profile, _ = Profile.objects.get_or_create(user=user)
    return profile


def get_display_name(user):
    profile = get_profile(user)

    if profile.display_name:
        return profile.display_name

    return user.get_full_name() or user.username


def get_photo_url(user):
    profile = get_profile(user)

    if profile.profile_picture:
        try:
            return profile.profile_picture.url
        except Exception:
            return ""

    return ""


def hidden_ids_for(user):
    if hidden_user_ids_for:
        return hidden_user_ids_for(user)

    return set()


def blocked_between(user, other_user):
    if block_exists_between:
        return block_exists_between(user, other_user)

    return False


def profile_identity_is_complete(profile):
    if not profile:
        return False

    return not identity_repair_issues(
        profile.user,
        profile,
    )


def target_genders_for(preference):
    if preference == Profile.INTERESTED_IN_WOMEN:
        return [Profile.GENDER_WOMAN]

    if preference == Profile.INTERESTED_IN_MEN:
        return [Profile.GENDER_MAN]

    if preference == Profile.INTERESTED_IN_EVERYONE:
        return [
            value
            for value, _label in Profile.GENDER_CHOICES
        ]

    return []


def preferences_accepting_gender(gender):
    audience = PROFILE_GENDER_TO_AUDIENCE.get(gender)

    if audience:
        return [
            audience,
            Profile.INTERESTED_IN_EVERYONE,
        ]

    if gender in {
        Profile.GENDER_NON_BINARY,
        Profile.GENDER_OTHER,
    }:
        return [Profile.INTERESTED_IN_EVERYONE]

    return []


def discoverable_profiles_for(
    viewer,
    *,
    exclude_acted=True,
):
    """
    Return profiles that are safe and mutually compatible.

    Location is deliberately not filtered yet because Heartly does not have
    reliable structured location or distance-preference data.
    """
    viewer_profile = get_profile(viewer)

    if not profile_identity_is_complete(viewer_profile):
        return Profile.objects.none()

    if (
        settings.HEARTLY_REQUIRE_VERIFIED_EMAIL
        and not viewer_profile.email_verified
    ):
        return Profile.objects.none()

    (
        oldest_dob_exclusive,
        youngest_dob_inclusive,
    ) = legal_birth_date_bounds()

    target_genders = target_genders_for(
        viewer_profile.interested_in
    )
    accepting_preferences = preferences_accepting_gender(
        viewer_profile.gender
    )

    if not target_genders or not accepting_preferences:
        return Profile.objects.none()

    profiles = (
        Profile.objects
        .select_related("user")
        .prefetch_related("interests")
        .filter(
            user__is_active=True,
            user__is_staff=False,
            user__date_of_birth__gt=(
                oldest_dob_exclusive
            ),
            user__date_of_birth__lte=(
                youngest_dob_inclusive
            ),
            profile_visible=True,
            hidden_by_moderation=False,
            age__gte=18,
            age__lte=100,
            gender__in=target_genders,
            interested_in__in=accepting_preferences,
        )
        .exclude(user=viewer)
        .exclude(display_name="")
        .exclude(user_id__in=hidden_ids_for(viewer))
    )

    if settings.HEARTLY_REQUIRE_VERIFIED_EMAIL:
        profiles = profiles.filter(
            email_verified=True
        )

    eligible_profile_ids = [
        profile.id
        for profile in profiles
        if profile_identity_is_complete(profile)
    ]
    profiles = profiles.filter(
        id__in=eligible_profile_ids
    )

    if exclude_acted:
        acted_user_ids = MatchAction.objects.filter(
            from_user=viewer,
        ).values_list("to_user_id", flat=True)

        profiles = profiles.exclude(
            user_id__in=acted_user_ids
        )

    return profiles.order_by("-updated_at")


def match_error_response(
    request,
    message,
    *,
    status=400,
):
    if is_ajax_request(request):
        return JsonResponse(
            {
                "ok": False,
                "matched": False,
                "error": message,
            },
            status=status,
        )

    messages.error(request, message)
    return redirect("matches:discover")


def create_match_notification(recipient, actor):
    if Notification is None:
        return

    actor_name = get_display_name(actor)

    try:
        notification_data = {
            "recipient": recipient,
            "actor": actor,
        }

        if model_has_field(
            Notification,
            "notification_type",
        ):
            notification_data["notification_type"] = getattr(
                Notification,
                "TYPE_MATCH",
                "match",
            )

        if model_has_field(Notification, "title"):
            notification_data["title"] = "New match"

        if model_has_field(Notification, "message"):
            notification_data["message"] = (
                f"You and {actor_name} matched. "
                "Start chatting now."
            )

        if model_has_field(Notification, "url"):
            notification_data["url"] = reverse(
                "matches:your_matches"
            )

        if model_has_field(
            Notification,
            "related_object_type",
        ):
            notification_data[
                "related_object_type"
            ] = "matches.mutualmatch"

        if model_has_field(
            Notification,
            "related_object_id",
        ):
            notification_data[
                "related_object_id"
            ] = actor.id

        Notification.objects.create(**notification_data)
    except Exception:
        logger.exception(
            "Could not create match notification.",
            extra={
                "recipient_id": recipient.id,
                "actor_id": actor.id,
            },
        )


def send_live_match_notification(recipient, actor):
    try:
        channel_layer = get_channel_layer()

        if not channel_layer:
            return

        actor_name = get_display_name(actor)
        actor_photo = get_photo_url(actor)

        async_to_sync(channel_layer.group_send)(
            f"heartly_user_{recipient.id}",
            {
                "type": "notification.event",
                "payload": {
                    "type": "match",
                    "title": "New match",
                    "message": (
                        f"You and {actor_name} matched."
                    ),
                    "actor_id": actor.id,
                    "actor_name": actor_name,
                    "actor_photo": actor_photo,
                    "url": reverse(
                        "matches:your_matches"
                    ),
                },
            },
        )
    except Exception:
        logger.exception(
            "Could not send live match notification.",
            extra={
                "recipient_id": recipient.id,
                "actor_id": actor.id,
            },
        )


def notify_new_match(user_a, user_b):
    create_match_notification(user_a, user_b)
    create_match_notification(user_b, user_a)

    send_live_match_notification(user_a, user_b)
    send_live_match_notification(user_b, user_a)


@login_required
def discover(request):
    search_query = request.GET.get("q", "").strip()
    viewer_profile = get_profile(request.user)
    viewer_issues = identity_repair_issues(
        request.user,
        viewer_profile,
    )

    if viewer_issues:
        return render(
            request,
            "matches/discover_identity_required.html",
            {
                "profiles": Profile.objects.none(),
                "viewer_profile": viewer_profile,
                "viewer_profile_complete": False,
                "identity_issues": identity_issue_messages(
                    request.user,
                    viewer_profile,
                ),
                "search_query": search_query,
            },
        )

    if (
        settings.HEARTLY_REQUIRE_VERIFIED_EMAIL
        and not viewer_profile.email_verified
    ):
        return render(
            request,
            "matches/discover_email_required.html",
            {
                "profiles": Profile.objects.none(),
                "viewer_profile": viewer_profile,
                "viewer_profile_complete": True,
                "identity_issues": [],
                "search_query": search_query,
            },
        )

    profiles = discoverable_profiles_for(request.user)

    if search_query:
        profiles = profiles.filter(
            build_profile_search_query(search_query)
        ).distinct()

    return render(
        request,
        "matches/discover.html",
        {
            "profiles": profiles,
            "viewer_profile": viewer_profile,
            "viewer_profile_complete": True,
            "identity_issues": [],
            "search_query": search_query,
        },
    )


@login_required
@require_POST
def swipe(request, user_id, action):
    if action not in (
        MatchAction.LIKE,
        MatchAction.PASS,
    ):
        return match_error_response(
            request,
            "Invalid match action.",
        )

    viewer_profile = get_profile(request.user)

    if identity_repair_issues(
        request.user,
        viewer_profile,
    ):
        return match_error_response(
            request,
            (
                "Complete your identity details before "
                "using Discover."
            ),
            status=403,
        )

    if (
        settings.HEARTLY_REQUIRE_VERIFIED_EMAIL
        and not viewer_profile.email_verified
    ):
        return match_error_response(
            request,
            "Verify your email before using Discover.",
            status=403,
        )

    target_profile = (
        discoverable_profiles_for(
            request.user,
            exclude_acted=False,
        )
        .filter(user_id=user_id)
        .first()
    )

    if target_profile is None:
        return match_error_response(
            request,
            "This profile is not available for matching.",
            status=404,
        )

    target_user = target_profile.user

    if blocked_between(request.user, target_user):
        return match_error_response(
            request,
            "This profile is not available.",
            status=403,
        )

    matched = False
    match_created = False
    match = None

    with transaction.atomic():
        MatchAction.objects.update_or_create(
            from_user=request.user,
            to_user=target_user,
            defaults={"action": action},
        )

        if action == MatchAction.LIKE:
            reciprocal_like = MatchAction.objects.filter(
                from_user=target_user,
                to_user=request.user,
                action=MatchAction.LIKE,
            ).exists()

            if reciprocal_like:
                match, match_created = (
                    MutualMatch.create_safe(
                        request.user,
                        target_user,
                        return_created=True,
                    )
                )
                matched = match is not None

    if action == MatchAction.LIKE:
        notify_profile_like(
            request.user,
            target_user,
            active=not matched,
        )
    else:
        notify_profile_like(
            request.user,
            target_user,
            active=False,
        )

    if match_created:
        notify_mutual_match(
            match,
            request.user,
            target_user,
        )

    if is_ajax_request(request):
        return JsonResponse(
            {
                "ok": True,
                "matched": matched,
            }
        )

    if matched:
        messages.success(
            request,
            (
                "You matched with "
                f"{get_display_name(target_user)}."
            ),
        )

    return redirect("matches:discover")


@login_required
def your_matches(request):
    hidden_ids = hidden_ids_for(request.user)

    matches = (
        MutualMatch.objects
        .filter(
            Q(user_one=request.user)
            | Q(user_two=request.user)
        )
        .exclude(user_one_id__in=hidden_ids)
        .exclude(user_two_id__in=hidden_ids)
        .select_related(
            "user_one",
            "user_two",
            "user_one__profile",
            "user_two__profile",
        )
        .order_by("-created_at")
    )

    match_cards = []

    for match in matches:
        other_user = (
            match.user_two
            if match.user_one == request.user
            else match.user_one
        )

        if (
            not other_user.is_active
            or blocked_between(
                request.user,
                other_user,
            )
        ):
            continue

        other_profile = getattr(
            other_user,
            "profile",
            None,
        )

        if (
            other_profile is None
            or not other_profile.profile_visible
            or other_profile.hidden_by_moderation
        ):
            continue

        match_cards.append(
            {
                "match": match,
                "other_user": other_user,
                "other_profile": other_profile,
            }
        )

    return render(
        request,
        "matches/your_matches.html",
        {"match_cards": match_cards},
    )
