from asgiref.sync import async_to_sync

from channels.layers import get_channel_layer
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from profiles.models import Profile

from .models import MatchAction, MutualMatch


try:
    from profiles.blocking import hidden_user_ids_for, block_exists_between
except Exception:
    hidden_user_ids_for = None
    block_exists_between = None


try:
    from notifications.models import Notification
except Exception:
    Notification = None


User = get_user_model()

def build_profile_search_query(search_query):
    search_filter = (
        Q(user__username__icontains=search_query)
        | Q(user__first_name__icontains=search_query)
        | Q(user__last_name__icontains=search_query)
    )

    if model_has_field(Profile, "display_name"):
        search_filter |= Q(display_name__icontains=search_query)

    if model_has_field(Profile, "name"):
        search_filter |= Q(name__icontains=search_query)

    if model_has_field(Profile, "bio"):
        search_filter |= Q(bio__icontains=search_query)

    return search_filter

def get_profile(user):
    profile, created = Profile.objects.get_or_create(user=user)
    return profile


def get_display_name(user):
    profile = get_profile(user)

    if getattr(profile, "display_name", None):
        return profile.display_name

    return user.get_full_name() or user.username


def get_photo_url(user):
    profile = get_profile(user)

    if getattr(profile, "profile_picture", None):
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


def model_has_field(model, field_name):
    return any(field.name == field_name for field in model._meta.fields)


def mutual_match_exists(user_a, user_b):
    return MutualMatch.objects.filter(
        Q(user_one=user_a, user_two=user_b)
        | Q(user_one=user_b, user_two=user_a)
    ).exists()


def create_match_notification(recipient, actor):
    if Notification is None:
        return

    actor_name = get_display_name(actor)

    try:
        notification_data = {
            "recipient": recipient,
            "actor": actor,
        }

        if model_has_field(Notification, "notification_type"):
            notification_data["notification_type"] = getattr(Notification, "TYPE_MATCH", "match")

        if model_has_field(Notification, "title"):
            notification_data["title"] = "New match"

        if model_has_field(Notification, "message"):
            notification_data["message"] = f"You and {actor_name} matched. Start chatting now."

        if model_has_field(Notification, "url"):
            notification_data["url"] = reverse("matches:your_matches")

        if model_has_field(Notification, "related_object_type"):
            notification_data["related_object_type"] = "matches.mutualmatch"

        if model_has_field(Notification, "related_object_id"):
            notification_data["related_object_id"] = actor.id

        Notification.objects.create(**notification_data)
    except Exception:
        return


def send_live_match_notification(recipient, actor):
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
                "message": f"You and {actor_name} matched.",
                "actor_id": actor.id,
                "actor_name": actor_name,
                "actor_photo": actor_photo,
                "url": reverse("matches:your_matches"),
            },
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

    viewer_profile, created = Profile.objects.get_or_create(user=request.user)

    acted_user_ids = MatchAction.objects.filter(
        from_user=request.user,
    ).values_list("to_user_id", flat=True)

    hidden_ids = hidden_ids_for(request.user)

    profiles = (
        Profile.objects
        .select_related("user")
        .prefetch_related("interests")
        .filter(profile_visible=True)
        .exclude(user=request.user)
        .exclude(user_id__in=acted_user_ids)
        .exclude(user_id__in=hidden_ids)
        .order_by("-updated_at")
    )

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
            "search_query": search_query,
        },
    )


@login_required
@require_POST
def swipe(request, user_id, action):
    if action not in (MatchAction.LIKE, MatchAction.PASS):
        return redirect("matches:discover")

    target_user = get_object_or_404(User, id=user_id)

    if target_user == request.user:
        return redirect("matches:discover")

    if blocked_between(request.user, target_user):
        messages.error(request, "This profile is not available.")
        return redirect("matches:discover")

    MatchAction.objects.update_or_create(
        from_user=request.user,
        to_user=target_user,
        defaults={"action": action},
    )

    matched = False

    if action == MatchAction.LIKE:
        reciprocal_like = MatchAction.objects.filter(
            from_user=target_user,
            to_user=request.user,
            action=MatchAction.LIKE,
        ).exists()

        if reciprocal_like:
            already_matched = mutual_match_exists(request.user, target_user)

            MutualMatch.create_safe(request.user, target_user)

            matched = True

            if not already_matched:
                notify_new_match(request.user, target_user)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"matched": matched})

    if matched:
        messages.success(request, f"You matched with {get_display_name(target_user)}.")

    return redirect("matches:discover")


@login_required
def your_matches(request):
    hidden_ids = hidden_ids_for(request.user)

    matches = (
        MutualMatch.objects
        .filter(Q(user_one=request.user) | Q(user_two=request.user))
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
        other_user = match.user_two if match.user_one == request.user else match.user_one

        if blocked_between(request.user, other_user):
            continue

        match_cards.append(
            {
                "match": match,
                "other_user": other_user,
                "other_profile": getattr(other_user, "profile", None),
            }
        )

    return render(
        request,
        "matches/your_matches.html",
        {"match_cards": match_cards},
    )