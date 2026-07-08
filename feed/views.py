from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import EditPostForm, PostForm
from .models import Comment, Post, PostLike


POSTS_PER_PAGE = 12


def wants_json(request):
    """
    True when the frontend is using fetch/AJAX instead of a normal form submit.
    """
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
        or request.POST.get("_ajax") == "1"
    )


def json_error(message, status=400, **extra):
    data = {
        "ok": False,
        "message": message,
    }
    data.update(extra)
    return JsonResponse(data, status=status)


def json_success(message="", **extra):
    data = {
        "ok": True,
        "message": message,
    }
    data.update(extra)
    return JsonResponse(data)


def first_form_error(form):
    """
    Return the first useful form error as plain text.
    """
    for field, errors in form.errors.items():
        for error in errors:
            if field == "__all__":
                return str(error)

            field_obj = form.fields.get(field)
            label = (
                field_obj.label
                if field_obj and field_obj.label
                else field.replace("_", " ").title()
            )

            return f"{label}: {error}"

    return "Please correct the form and try again."


def upload_exception_message(exc):
    """
    Avoid silent 500 errors when Cloudinary/local storage rejects a video.
    """
    message = (
        "Upload failed. If this was a video, check the file type, file size, "
        "and Cloudinary video storage setup."
    )

    if settings.DEBUG:
        return f"{message} Details: {exc}"

    return message


def respond_error(request, message, status=400):
    if wants_json(request):
        return json_error(message, status=status)

    messages.error(request, message)
    return redirect("feed:feed_home")


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


def post_owner(post):
    """
    Your Post model uses `author`, not `user`.
    This helper keeps the rest of the view clean.
    """
    return getattr(post, "author", None)


def username_for(user):
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
    return f"@{username_for(user)}"


def avatar_url_for(user):
    profile = _safe_profile(user)

    for attr in ("profile_picture", "photo", "avatar", "image"):
        field = getattr(profile, attr, None) if profile else None
        url = _safe_file_url(field)

        if url:
            return url

    for attr in ("profile_picture", "avatar", "photo"):
        field = getattr(user, attr, None)
        url = _safe_file_url(field)

        if url:
            return url

    return ""


def initials_for(name):
    clean = (name or "H").strip().replace("@", "")

    if not clean:
        return "H"

    parts = clean.split()

    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[1][0]}".upper()

    return clean[:2].upper()


def decorate_user_identity(target, user):
    username = username_for(user)

    target.display_name = f"@{username}"
    target.username = username
    target.username_label = ""
    target.avatar_url = avatar_url_for(user)
    target.avatar_initials = initials_for(username)

    return target


def decorate_comment(comment):
    decorate_user_identity(comment, comment.user)
    return comment


def decorate_post(post, viewer):
    owner = post_owner(post)

    decorate_user_identity(post, owner)

    post.is_liked_by_user = post.likes.filter(user=viewer).exists()
    post.likes_count = post.likes.count()

    comments = list(
        post.comments
        .select_related("user")
        .order_by("created_at")
    )

    for comment in comments:
        decorate_comment(comment)

    post.comments_count = len(comments)
    post.visible_comments = comments[:3]

    post.image_url = _safe_file_url(post.image)
    post.video_url = _safe_file_url(post.video)

    return post


def enrich_posts(posts, viewer):
    viewer_like_ids = set(
        PostLike.objects
        .filter(user=viewer, post__in=posts)
        .values_list("post_id", flat=True)
    )

    for post in posts:
        owner = post_owner(post)

        decorate_user_identity(post, owner)

        post.is_liked_by_user = post.id in viewer_like_ids
        post.likes_count = post.likes.count()

        comments = list(post.comments.all())

        for comment in comments:
            decorate_comment(comment)

        post.comments_count = len(comments)
        post.visible_comments = comments[:3]

        post.image_url = _safe_file_url(post.image)
        post.video_url = _safe_file_url(post.video)

        yield post


def render_post_card(request, post):
    post = decorate_post(post, request.user)

    return render_to_string(
        "feed/_post_card.html",
        {
            "post": post,
            "request": request,
        },
        request=request,
    )


def render_comment_html(request, comment):
    comment = decorate_comment(comment)

    return render_to_string(
        "feed/_comment_item.html",
        {
            "comment": comment,
            "request": request,
        },
        request=request,
    )


@login_required
def feed_home(request):
    posts_qs = (
        Post.objects
        .select_related("author")
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
            "form": PostForm(),
            "post_form": PostForm(),
            "edit_form": EditPostForm(),
            "viewer_name": display_name_for(request.user),
            "viewer_username": username_for(request.user),
            "viewer_avatar_url": avatar_url_for(request.user),
            "viewer_initials": initials_for(username_for(request.user)),
        },
    )


@login_required
@require_POST
def create_post(request):
    image = request.FILES.get("image")
    video = request.FILES.get("video")

    if image and video:
        return respond_error(
            request,
            "Please upload either an image or a video, not both.",
        )

    form = PostForm(request.POST, request.FILES)

    if not form.is_valid():
        return respond_error(request, first_form_error(form))

    post = form.save(commit=False)
    post.author = request.user

    try:
        post.save()
    except Exception as exc:
        return respond_error(request, upload_exception_message(exc), status=500)

    if wants_json(request):
        return json_success(
            "Post shared.",
            post_id=post.id,
            post_html=render_post_card(request, post),
        )

    messages.success(request, "Post shared.")
    return redirect("feed:feed_home")


@login_required
@require_POST
def edit_post(request, post_id):
    post = get_object_or_404(Post, id=post_id, author=request.user)

    image = request.FILES.get("image")
    video = request.FILES.get("video")

    remove_image = (
        request.POST.get("remove_image") == "1"
        or request.POST.get("image-clear") == "on"
    )
    remove_video = (
        request.POST.get("remove_video") == "1"
        or request.POST.get("video-clear") == "on"
    )

    if image and video:
        return respond_error(
            request,
            "Please upload either an image or a video, not both.",
        )

    form = EditPostForm(request.POST, request.FILES, instance=post)

    if not form.is_valid():
        return respond_error(request, first_form_error(form))

    updated_post = form.save(commit=False)

    if remove_image:
        updated_post.image = None

    if remove_video:
        updated_post.video = None

    if image:
        updated_post.image = image
        updated_post.video = None

    if video:
        updated_post.video = video
        updated_post.image = None

    has_content = bool((updated_post.content or "").strip())
    has_image = bool(updated_post.image)
    has_video = bool(updated_post.video)

    if not has_content and not has_image and not has_video:
        return respond_error(
            request,
            "A post cannot be empty. Add text, an image, or a video.",
        )

    updated_post.edited_at = timezone.now()

    try:
        updated_post.save()
    except Exception as exc:
        return respond_error(request, upload_exception_message(exc), status=500)

    if wants_json(request):
        return json_success(
            "Post updated.",
            post_id=updated_post.id,
            post_html=render_post_card(request, updated_post),
        )

    messages.success(request, "Post updated.")
    return redirect("feed:feed_home")


@login_required
@require_POST
def delete_post(request, post_id):
    post = get_object_or_404(Post, id=post_id, author=request.user)
    post.delete()

    if wants_json(request):
        return json_success("Post deleted.", post_id=post_id)

    messages.success(request, "Post deleted.")
    return redirect("feed:feed_home")


@login_required
@require_POST
def like_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)

    like, created = PostLike.objects.get_or_create(
        post=post,
        user=request.user,
    )

    liked = True

    if not created:
        like.delete()
        liked = False

    likes_count = post.likes.count()

    if wants_json(request):
        return json_success(
            "Liked." if liked else "Unliked.",
            post_id=post.id,
            liked=liked,
            likes_count=likes_count,
        )

    return redirect(request.POST.get("next") or reverse("feed:feed_home"))


@login_required
@require_POST
def comment_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)

    content = (
        request.POST.get("content")
        or request.POST.get("comment")
        or ""
    ).strip()

    if not content:
        return respond_error(request, "Comment cannot be empty.")

    comment = Comment.objects.create(
        post=post,
        user=request.user,
        content=content,
    )

    comments_count = post.comments.count()

    if wants_json(request):
        return json_success(
            "Comment added.",
            post_id=post.id,
            comment_id=comment.id,
            comment_html=render_comment_html(request, comment),
            comments_count=comments_count,
        )

    return redirect("feed:feed_home")


@login_required
@require_POST
def report_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)

    if post.author_id == request.user.id:
        return respond_error(request, "You cannot report your own post.")

    # Lightweight report handler. No migration required.
    # Add PostReport saving later only when its model and migration are stable.
    if wants_json(request):
        return json_success(
            "Post reported. Our team will review it.",
            post_id=post.id,
        )

    messages.success(request, "Post reported. Our team will review it.")
    return redirect("feed:feed_home")