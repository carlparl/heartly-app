from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .blocking import block_exists_between, user_is_hidden_for
from .forms import (
    IdentityRepairForm,
    InterestForm,
    ProfileForm,
    ProfilePhotoForm,
    profile_version_value,
)
from .identity import (
    identity_issue_messages,
    identity_repair_issues,
)
from .models import Interest, Profile, ProfileReport, UserBlock


try:
    from feed.models import Post, PostLike
except Exception:
    Post = None
    PostLike = None


try:
    from notifications.models import Notification
except Exception:
    Notification = None


User = get_user_model()

STALE_PROFILE_MESSAGE = (
    "This profile was updated in another request. "
    "Refresh the page before saving again."
)


DEFAULT_INTERESTS = [
    "Music", "Movies", "TV Shows", "Anime", "K-Dramas", "Documentaries",
    "Comedy", "Theatre", "Concerts", "Podcasts", "Travel", "Food",
    "Cooking", "Baking", "Fashion", "Photography", "Shopping",
    "Interior Design", "Self Care", "Journaling", "Art", "Drawing",
    "Painting", "Graphic Design", "Content Creation", "Writing", "Poetry",
    "Dancing", "Singing", "Crafts", "Sports", "Football", "Basketball",
    "Volleyball", "Running", "Gym", "Fitness", "Yoga", "Swimming",
    "Cycling", "Gaming", "Reading", "Books", "Chess", "Board Games",
    "Gardening", "Pets", "Outdoors", "Hiking", "Camping", "Tech",
    "Coding", "AI", "Startups", "Science", "Learning Languages",
    "History", "Business", "Finance", "Entrepreneurship", "Kindness",
    "Deep Conversations", "Friendship", "Family", "Volunteering",
    "Community", "Personal Growth", "Motivation", "Peaceful Living",
]


def model_has_field(model, field_name):
    return any(field.name == field_name for field in model._meta.fields)


def ensure_default_interests():
    for name in DEFAULT_INTERESTS:
        Interest.objects.get_or_create(name=name)


def get_profile(user):
    profile, created = Profile.objects.get_or_create(user=user)
    return profile


def get_display_name(user):
    profile = get_profile(user)

    if getattr(profile, "display_name", None):
        return profile.display_name

    return user.get_full_name() or user.username


def attach_profile_template_fields(profile):
    display_name = (
        getattr(profile, "display_name", "")
        or profile.user.get_full_name()
        or profile.user.username
    )

    profile.safe_display_name = display_name

    try:
        profile.photo_url = profile.primary_photo_url
    except Exception:
        profile.photo_url = ""

    return profile


def profile_is_available(profile):
    if not profile:
        return False

    if getattr(profile, "profile_visible", True) is False:
        return False

    if model_has_field(Profile, "hidden_by_moderation"):
        if getattr(profile, "hidden_by_moderation", False):
            return False

    return True


def visible_posts_for(user):
    if Post is None:
        return []

    queryset = Post.objects.filter(author=user).order_by("-created_at")

    if model_has_field(Post, "hidden_by_moderation"):
        queryset = queryset.filter(hidden_by_moderation=False)

    return queryset


def visible_media_posts_for(user):
    if Post is None:
        return []

    queryset = visible_posts_for(user)

    if not hasattr(queryset, "filter"):
        return []

    return queryset.filter(
        (Q(image__isnull=False) & ~Q(image=""))
        | (Q(video__isnull=False) & ~Q(video=""))
    )


def safe_file_url(file_field):
    if not file_field:
        return ""

    try:
        return file_field.url
    except Exception:
        return ""


def profile_summary_context(user):
    profile = attach_profile_template_fields(get_profile(user))
    posts = visible_posts_for(user)
    media_posts = visible_media_posts_for(user)

    posts_count = posts.count() if hasattr(posts, "count") else 0
    media_count = media_posts.count() if hasattr(media_posts, "count") else 0

    likes_count = 0
    if PostLike is not None:
        likes_count = PostLike.objects.filter(user=user).count()

    block_list = (
        UserBlock.objects
        .filter(blocker=user)
        .select_related("blocked")
        .order_by("-created_at")
    )

    return {
        "profile": profile,
        "viewed_profile": profile,
        "viewed_user": user,
        "display_name": get_display_name(user),
        "posts": posts,
        "posts_count": posts_count,
        "likes_count": likes_count,
        "media_count": media_count,
        "block_list": block_list,
        "is_owner": True,
        "is_blocked": False,
    }


def clear_notifications_between(user_one, user_two):
    if Notification is None:
        return

    Notification.objects.filter(
        Q(recipient=user_one, actor=user_two)
        | Q(recipient=user_two, actor=user_one)
    ).update(
        is_read=True,
        is_resolved=True,
        resolved_at=timezone.now(),
    )


@login_required
def profile_home(request):
    return render(
        request,
        "profiles/profile.html",
        profile_summary_context(request.user),
    )


@login_required
def profile_details(request):
    ensure_default_interests()
    context = profile_summary_context(request.user)
    profile = context["profile"]
    context.update(
        {
            "interests": profile.interests.all().order_by("name"),
        }
    )
    return render(request, "profiles/profile_details.html", context)


@login_required
def profile_activity(request):
    context = profile_summary_context(request.user)
    posts = context["posts"]

    if hasattr(posts, "select_related"):
        posts = posts.select_related("author", "author__profile").prefetch_related("likes", "comments")

    context.update({"posts": posts})
    return render(request, "profiles/profile_activity.html", context)


@login_required
def profile_media(request):
    context = profile_summary_context(request.user)
    profile = context["profile"]
    media_items = []

    gallery_photos = list(profile.photos.order_by("position", "id"))

    if gallery_photos:
        for photo in gallery_photos:
            photo_url = safe_file_url(photo.image)
            if not photo_url:
                continue

            media_items.append(
                {
                    "type": "Profile photo",
                    "url": photo_url,
                    "kind": "image",
                    "caption": (
                        "Primary profile photo"
                        if photo.position == 1
                        else f"Profile photo {photo.position}"
                    ),
                    "created_at": photo.created_at,
                }
            )
    else:
        profile_photo_url = safe_file_url(
            getattr(profile, "profile_picture", None)
        )
        if profile_photo_url:
            media_items.append(
                {
                    "type": "Profile photo",
                    "url": profile_photo_url,
                    "kind": "image",
                    "caption": "Primary profile photo",
                    "created_at": getattr(profile, "updated_at", None),
                }
            )

    media_posts = visible_media_posts_for(request.user)
    for post in media_posts[:60]:
        image_url = safe_file_url(getattr(post, "image", None))
        video_url = safe_file_url(getattr(post, "video", None))

        if image_url:
            media_items.append(
                {
                    "type": "Post photo",
                    "url": image_url,
                    "kind": "image",
                    "caption": getattr(post, "content", "") or "Photo post",
                    "created_at": getattr(post, "created_at", None),
                }
            )

        if video_url:
            media_items.append(
                {
                    "type": "Post video",
                    "url": video_url,
                    "kind": "video",
                    "caption": getattr(post, "content", "") or "Video post",
                    "created_at": getattr(post, "created_at", None),
                }
            )

    context.update({"media_items": media_items})
    return render(request, "profiles/profile_media.html", context)


def public_profile(request, user_id):
    target_user = get_object_or_404(User, id=user_id)
    profile, created = Profile.objects.get_or_create(user=target_user)

    if request.user.is_authenticated:
        if user_is_hidden_for(request.user, target_user):
            messages.error(request, "This profile is not available.")
            return redirect("matches:discover")
    else:
        if getattr(profile, "profile_visible", True) is False:
            return redirect("welcome")

    if getattr(profile, "hidden_by_moderation", False):
        messages.error(request, "This profile is not available.")
        return redirect("matches:discover")

    return render(
        request,
        "profiles/public_profile.html",
        {
            "profile_user": target_user,
            "profile": profile,
        },
    )


@login_required
def repair_identity(request):
    profile = get_profile(request.user)
    next_url = (
        request.POST.get("next")
        or request.GET.get("next")
        or ""
    ).strip()

    if request.method == "POST":
        form = IdentityRepairForm(
            request.POST,
            user=request.user,
            profile=profile,
        )

        if form.is_valid():
            form.save()
            profile.refresh_from_db()
            request.user.refresh_from_db()

            remaining_issues = identity_repair_issues(
                request.user,
                profile,
            )

            if not remaining_issues:
                messages.success(
                    request,
                    "Your identity details are confirmed.",
                )

                if (
                    next_url
                    and url_has_allowed_host_and_scheme(
                        next_url,
                        allowed_hosts={request.get_host()},
                        require_https=request.is_secure(),
                    )
                ):
                    return redirect(next_url)

                return redirect("matches:discover")

            messages.error(
                request,
                "Some identity details still need attention.",
            )
    else:
        form = IdentityRepairForm(
            user=request.user,
            profile=profile,
        )

    return render(
        request,
        "profiles/identity_repair.html",
        {
            "form": form,
            "profile": profile,
            "identity_issues": identity_issue_messages(
                request.user,
                profile,
            ),
            "next_url": next_url,
        },
    )

@login_required
@never_cache
def edit_profile(request):
    ensure_default_interests()
    profile = get_profile(request.user)

    if request.method == "POST":
        form = ProfileForm(
            request.POST,
            request.FILES,
            instance=profile,
            user=request.user,
        )
        photo_form = ProfilePhotoForm(
            request.POST,
            request.FILES,
            profile=profile,
        )

        profile_is_valid = form.is_valid()
        photos_are_valid = photo_form.is_valid()

        profile_saved = False

        if profile_is_valid and photos_are_valid:
            with transaction.atomic():
                locked_profile = (
                    Profile.objects.select_for_update().get(pk=profile.pk)
                )
                submitted_version = (
                    form.cleaned_data.get("profile_version") or ""
                ).strip()

                profile = locked_profile

                if submitted_version != profile_version_value(locked_profile):
                    form.add_error(None, STALE_PROFILE_MESSAGE)
                else:
                    locked_form = ProfileForm(
                        request.POST,
                        request.FILES,
                        instance=locked_profile,
                        user=request.user,
                    )
                    photo_form.bind_profile(locked_profile)

                    if locked_form.is_valid():
                        locked_form.save()
                        photo_form.save()
                        form = locked_form
                        profile_saved = True
                    else:
                        form = locked_form

        if profile_saved:
            messages.success(request, "Profile updated.")
            return redirect("profiles:profile_home")
    else:
        form = ProfileForm(instance=profile, user=request.user)
        photo_form = ProfilePhotoForm(profile=profile)

    selected_interests = list(profile.interests.all().order_by("name")[:12])
    selected_interest_count = profile.interests.count()
    extra_interest_count = max(selected_interest_count - len(selected_interests), 0)

    if selected_interests:
        interest_chips = selected_interests
    else:
        interest_chips = list(Interest.objects.all().order_by("name")[:10])

    photos_by_position = {
        photo.position: photo
        for photo in profile.photos.order_by("position", "id")
    }
    photo_slots = [
        {
            "position": position,
            "photo": photos_by_position.get(position),
            "field": photo_form[f"photo_{position}"],
            "remove_field": photo_form[f"remove_{position}"],
        }
        for position in range(1, 5)
    ]

    return render(
        request,
        "profiles/edit_profile.html",
        {
            "form": form,
            "photo_form": photo_form,
            "photo_slots": photo_slots,
            "profile_photo_url": profile.primary_photo_url,
            "profile": profile,
            "interest_chips": interest_chips,
            "selected_interest_count": selected_interest_count,
            "extra_interest_count": extra_interest_count,
        },
    )


@login_required
@never_cache
def edit_interests(request):
    ensure_default_interests()

    profile = get_profile(request.user)

    if request.method == "POST":
        form = InterestForm(request.POST, profile=profile)
        interests_saved = False

        if form.is_valid():
            with transaction.atomic():
                locked_profile = (
                    Profile.objects.select_for_update().get(pk=profile.pk)
                )
                submitted_version = (
                    form.cleaned_data.get("profile_version") or ""
                ).strip()

                profile = locked_profile

                if submitted_version != profile_version_value(locked_profile):
                    form.add_error(None, STALE_PROFILE_MESSAGE)
                else:
                    locked_profile.interests.set(
                        form.cleaned_data.get("interests", [])
                    )
                    locked_profile.save(update_fields=["updated_at"])
                    interests_saved = True

        if interests_saved:
            messages.success(request, "Interests updated.")
            return redirect("profiles:profile_home")
    else:
        form = InterestForm(profile=profile)

    return render(
        request,
        "profiles/interests.html",
        {
            "form": form,
            "profile": profile,
        },
    )


@login_required
@require_POST
def report_profile(request, user_id):
    target_user = get_object_or_404(User, id=user_id)

    if target_user == request.user:
        messages.error(request, "You cannot report yourself.")
        return redirect("profiles:profile_home")

    if block_exists_between(request.user, target_user):
        messages.error(request, "This profile is not available.")
        return redirect("matches:discover")

    reason = request.POST.get("reason", "").strip() or "other"
    details = request.POST.get("details", "").strip()

    report_fields = {field.name for field in ProfileReport._meta.fields}
    create_data = {}

    if "reported_user" in report_fields:
        create_data["reported_user"] = target_user
    elif "user" in report_fields:
        create_data["user"] = target_user

    if "reporter" in report_fields:
        create_data["reporter"] = request.user
    elif "reported_by" in report_fields:
        create_data["reported_by"] = request.user

    if "reason" in report_fields:
        create_data["reason"] = reason

    if "details" in report_fields:
        create_data["details"] = details
    elif "description" in report_fields:
        create_data["description"] = details

    existing_filter = {}

    if "reported_user" in create_data:
        existing_filter["reported_user"] = target_user
    elif "user" in create_data:
        existing_filter["user"] = target_user

    if "reporter" in create_data:
        existing_filter["reporter"] = request.user
    elif "reported_by" in create_data:
        existing_filter["reported_by"] = request.user

    if existing_filter and ProfileReport.objects.filter(**existing_filter).exists():
        messages.info(request, "You already reported this profile.")
        return redirect("profiles:public_profile", user_id=target_user.id)

    ProfileReport.objects.create(**create_data)

    messages.success(request, "Profile reported. Thank you for helping keep Heartly safe.")
    return redirect("profiles:public_profile", user_id=target_user.id)


@login_required
@require_POST
def block_user(request, user_id):
    target_user = get_object_or_404(User, id=user_id)

    if target_user == request.user:
        messages.error(request, "You cannot block yourself.")
        return redirect("profiles:profile_home")

    UserBlock.objects.get_or_create(
        blocker=request.user,
        blocked=target_user,
    )

    clear_notifications_between(request.user, target_user)

    messages.success(request, f"{get_display_name(target_user)} has been blocked.")
    return redirect("profiles:profile_home")


@login_required
@require_POST
def unblock_user(request, user_id):
    target_user = get_object_or_404(User, id=user_id)

    UserBlock.objects.filter(
        blocker=request.user,
        blocked=target_user,
    ).delete()

    messages.success(request, f"{get_display_name(target_user)} has been unblocked.")
    return redirect("profiles:profile_home")


@login_required
@require_POST
def toggle_profile_visibility(request):
    profile = get_profile(request.user)
    profile.profile_visible = not profile.profile_visible
    profile.save(update_fields=["profile_visible"])

    messages.success(request, "Profile visibility updated.")
    return redirect("settings")


@login_required
@require_POST
def toggle_online_status(request):
    profile = get_profile(request.user)
    profile.show_online_status = not profile.show_online_status
    profile.save(update_fields=["show_online_status"])

    messages.success(request, "Online status setting updated.")
    return redirect("settings")


@login_required
@require_POST
def toggle_message_requests(request):
    profile = get_profile(request.user)
    profile.allow_message_requests = not profile.allow_message_requests
    profile.save(update_fields=["allow_message_requests"])

    messages.success(request, "Message request setting updated.")
    return redirect("settings")


@login_required
@require_POST
def toggle_safety_filters(request):
    profile = get_profile(request.user)
    profile.safety_filters_enabled = not profile.safety_filters_enabled
    profile.save(update_fields=["safety_filters_enabled"])

    messages.success(request, "Safety filter setting updated.")
    return redirect("settings")