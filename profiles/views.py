from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .blocking import block_exists_between, user_is_hidden_for
from .forms import InterestForm, ProfileForm
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
        profile.photo_url = profile.profile_picture.url if profile.profile_picture else ""
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
    profile = attach_profile_template_fields(get_profile(request.user))

    posts = visible_posts_for(request.user)
    posts_count = posts.count() if hasattr(posts, "count") else 0

    likes_count = 0

    if PostLike is not None:
        likes_count = PostLike.objects.filter(user=request.user).count()

    block_list = (
        UserBlock.objects
        .filter(blocker=request.user)
        .select_related("blocked")
        .order_by("-created_at")
    )

    return render(
        request,
        "profiles/profile.html",
        {
            "profile": profile,
            "viewed_profile": profile,
            "viewed_user": request.user,
            "display_name": get_display_name(request.user),
            "posts": posts,
            "posts_count": posts_count,
            "likes_count": likes_count,
            "block_list": block_list,
            "is_owner": True,
            "is_blocked": False,
        },
    )


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
def edit_profile(request):
    profile = get_profile(request.user)

    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=profile)

        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("profiles:profile_home")
    else:
        form = ProfileForm(instance=profile)

    return render(
        request,
        "profiles/edit_profile.html",
        {
            "form": form,
            "profile": profile,
        },
    )


@login_required
def edit_interests(request):
    ensure_default_interests()

    profile = get_profile(request.user)

    if request.method == "POST":
        try:
            form = InterestForm(request.POST, instance=profile)
        except TypeError:
            form = InterestForm(request.POST)

        if form.is_valid():
            if hasattr(form, "save"):
                form.save()
            else:
                profile.interests.set(form.cleaned_data.get("interests", []))
                profile.save()

            messages.success(request, "Interests updated.")
            return redirect("profiles:profile_home")
    else:
        try:
            form = InterestForm(instance=profile)
        except TypeError:
            form = InterestForm(initial={"interests": profile.interests.all()})

    return render(
        request,
        "profiles/edit_interests.html",
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