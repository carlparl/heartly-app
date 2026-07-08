from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Comment, Post, PostLike
from .validators import validate_image_upload, validate_video_upload


POSTS_PER_PAGE = 12


def _safe_file_url(file_field):
    if not file_field:
        return ""
    try:
        return file_field.url
    except Exception:
        return ""


def _safe_profile(user):
    try:
        return user.profile
    except Exception:
        return None


def username_for(user):
    """Return the public username label used in feed and comments."""
    username = (getattr(user, "username", "") or "").strip()
    if username:
        return username

    email = (getattr(user, "email", "") or "").strip()
    if email and "@" in email:
        return email.split("@", 1)[0]

    if email:
        return email

    return "heartly_user"


def display_name_for(user):
    """Prefer profile display name, then full name, then username/email fallback."""
    profile = _safe_profile(user)

    for attr in ("display_name", "name"):
        value = (getattr(profile, attr, "") or "").strip() if profile else ""
        if value:
            return value

    full_name = ""
    try:
        full_name = (user.get_full_name() or "").strip()
    except Exception:
        full_name = ""

    if full_name:
        return full_name

    username = username_for(user)
    if username:
        return username

    return "Heartly user"


def avatar_url_for(user):
    """Return the active profile image URL for a user, supporting old field names too."""
    profile = _safe_profile(user)

    for attr in ("profile_picture", "photo", "avatar", "image"):
        field = getattr(profile, attr, None) if profile else None
        url = _safe_file_url(field)
        if url:
            return url

    # Some projects store profile image directly on the custom user model.
    for attr in ("profile_picture", "avatar", "photo"):
        field = getattr(user, attr, None)
        url = _safe_file_url(field)
        if url:
            return url

    return ""


def initials_for(name):
    clean = (name or "H").strip()
    if not clean:
        return "H"
    parts = clean.split()
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[1][0]}".upper()
    return clean[:2].upper()


def decorate_user_identity(target, user):
    """Attach template-ready identity fields to posts and comments."""
    name = display_name_for(user)
    username = username_for(user)
    target.display_name = name
    target.username = username
    target.username_label = f"@{username}" if username else ""
    target.avatar_url = avatar_url_for(user)
    target.avatar_initials = initials_for(name or username)
    return target


def enrich_posts(posts, viewer):
    viewer_like_ids = set(
        PostLike.objects.filter(user=viewer, post__in=posts).values_list("post_id", flat=True)
    )

    for post in posts:
        decorate_user_identity(post, post.user)
        post.is_liked_by_user = post.id in viewer_like_ids
        post.likes_count = post.likes.count()

        comments = list(post.comments.all())
        for comment in comments:
            decorate_user_identity(comment, comment.user)

        post.comments_count = len(comments)
        post.visible_comments = comments[:3]
        post.image_url = _safe_file_url(post.image)
        post.video_url = _safe_file_url(post.video)
        yield post


@login_required
def feed_home(request):
    posts_qs = (
        Post.objects.select_related("user")
        .prefetch_related(
            "likes",
            Prefetch(
                "comments",
                queryset=Comment.objects.select_related("user").order_by("created_at"),
            ),
        )
        .order_by("-created_at")
    )

    paginator = Paginator(posts_qs, POSTS_PER_PAGE)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    posts = list(enrich_posts(list(page_obj.object_list), request.user))

    return render(
        request,
        "feed/feed.html",
        {
            "posts": posts,
            "page_obj": page_obj,
            "viewer_name": display_name_for(request.user),
            "viewer_username": username_for(request.user),
            "viewer_avatar_url": avatar_url_for(request.user),
            "viewer_initials": initials_for(display_name_for(request.user)),
        },
    )


@login_required
@require_POST
def create_post(request):
    content = (request.POST.get("content") or "").strip()
    image = request.FILES.get("image")
    video = request.FILES.get("video")

    if image and video:
        messages.error(request, "Please upload either an image or a video, not both.")
        return redirect("feed:feed_home")

    if not content and not image and not video:
        messages.error(request, "Write something or attach media before posting.")
        return redirect("feed:feed_home")

    image_error = validate_image_upload(image)
    if image_error:
        messages.error(request, image_error)
        return redirect("feed:feed_home")

    video_error = validate_video_upload(video)
    if video_error:
        messages.error(request, video_error)
        return redirect("feed:feed_home")

    Post.objects.create(
        user=request.user,
        content=content,
        image=image if image else None,
        video=video if video else None,
    )

    messages.success(request, "Post shared.")
    return redirect("feed:feed_home")


@login_required
@require_POST
def edit_post(request, post_id):
    post = get_object_or_404(Post, id=post_id, user=request.user)

    content = (request.POST.get("content") or "").strip()
    image = request.FILES.get("image")
    video = request.FILES.get("video")
    remove_image = request.POST.get("remove_image") == "1"
    remove_video = request.POST.get("remove_video") == "1"

    if image and video:
        messages.error(request, "Please upload either an image or a video, not both.")
        return redirect("feed:feed_home")

    image_error = validate_image_upload(image)
    if image_error:
        messages.error(request, image_error)
        return redirect("feed:feed_home")

    video_error = validate_video_upload(video)
    if video_error:
        messages.error(request, video_error)
        return redirect("feed:feed_home")

    post.content = content

    if remove_image:
        post.image = None
    if remove_video:
        post.video = None

    if image:
        post.image = image
        post.video = None
    if video:
        post.video = video
        post.image = None

    post.edited_at = timezone.now()
    post.save()

    messages.success(request, "Post updated.")
    return redirect("feed:feed_home")


@login_required
@require_POST
def delete_post(request, post_id):
    post = get_object_or_404(Post, id=post_id, user=request.user)
    post.delete()
    messages.success(request, "Post deleted.")
    return redirect("feed:feed_home")


@login_required
@require_POST
def like_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    like, created = PostLike.objects.get_or_create(post=post, user=request.user)

    if not created:
        like.delete()

    return redirect(request.POST.get("next") or reverse("feed:feed_home"))


@login_required
@require_POST
def comment_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    content = (request.POST.get("content") or request.POST.get("comment") or "").strip()

    if not content:
        messages.error(request, "Comment cannot be empty.")
        return redirect("feed:feed_home")

    Comment.objects.create(post=post, user=request.user, content=content)
    return redirect("feed:feed_home")


@login_required
@require_POST
def report_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)

    if post.user_id == request.user.id:
        messages.error(request, "You cannot report your own post.")
        return redirect("feed:feed_home")

    # Lightweight compatibility handler. Add a PostReport model later if you need staff review storage.
    messages.success(request, "Post reported. Our team will review it.")
    return redirect("feed:feed_home")
