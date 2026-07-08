from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import models
from .models import Post, Comment, PostLike


def _is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _field_exists(model_class, field_name):
    try:
        model_class._meta.get_field(field_name)
        return True
    except Exception:
        return False


def _author_field_for(model_class):
    if _field_exists(model_class, "author"):
        return "author"
    if _field_exists(model_class, "user"):
        return "user"
    return None


def _content_field_for(model_class):
    if _field_exists(model_class, "content"):
        return "content"
    if _field_exists(model_class, "text"):
        return "text"
    if _field_exists(model_class, "body"):
        return "body"
    return None


def _get_post_owner(post):
    if hasattr(post, "author"):
        return post.author
    if hasattr(post, "user"):
        return post.user
    return None


def _user_owns_post(post, user):
    owner = _get_post_owner(post)
    return owner == user


def _post_likes_count(post):
    return PostLike.objects.filter(post=post).count()


def _user_liked_post(post, user):
    user_field = _author_field_for(PostLike)

    if not user.is_authenticated or not user_field:
        return False

    lookup = {
        "post": post,
        user_field: user,
    }

    return PostLike.objects.filter(**lookup).exists()


def _create_like(post, user):
    user_field = _author_field_for(PostLike)

    if not user_field:
        raise Exception("PostLike model must have either a 'user' or 'author' field.")

    lookup = {
        "post": post,
        user_field: user,
    }

    like, created = PostLike.objects.get_or_create(**lookup)
    return like, created


@login_required
def feed_home(request):
    posts = Post.objects.all()

    if _field_exists(Post, "created_at"):
        posts = posts.order_by("-created_at")
    else:
        posts = posts.order_by("-id")

    context = {
        "posts": posts,
    }

    return render(request, "feed/feed.html", context)


@login_required
@require_POST
def create_post(request):
    content = request.POST.get("content", "").strip()
    image = request.FILES.get("image")
    video = request.FILES.get("video")

    if not content and not image and not video:
        if _is_ajax(request):
            return JsonResponse(
                {"ok": False, "error": "Add text, an image, or a video before posting."},
                status=400,
            )

        messages.error(request, "Add text, an image, or a video before posting.")
        return redirect("feed:feed_home")

    create_data = {}

    author_field = _author_field_for(Post)
    if author_field:
        create_data[author_field] = request.user

    if _field_exists(Post, "content"):
        create_data["content"] = content
    elif _field_exists(Post, "text"):
        create_data["text"] = content
    elif _field_exists(Post, "body"):
        create_data["body"] = content

    if image and _field_exists(Post, "image"):
        create_data["image"] = image

    if video and _field_exists(Post, "video"):
        create_data["video"] = video

    try:
        post = Post.objects.create(**create_data)
    except Exception as exc:
        if _is_ajax(request):
            return JsonResponse({"ok": False, "error": str(exc)}, status=500)

        messages.error(request, str(exc))
        return redirect("feed:feed_home")

    if _is_ajax(request):
        return JsonResponse(
            {
                "ok": True,
                "message": "Post created successfully.",
                "post_id": post.id,
            }
        )

    messages.success(request, "Post created successfully.")
    return redirect("feed:feed_home")


@login_required
@require_POST
def edit_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)

    if not _user_owns_post(post, request.user):
        raise PermissionDenied("You can only edit your own posts.")

    content = request.POST.get("content", "").strip()
    image = request.FILES.get("image")
    video = request.FILES.get("video")

    content_field = _content_field_for(Post)

    if content_field:
        setattr(post, content_field, content)

    if image and _field_exists(Post, "image"):
        post.image = image

    if video and _field_exists(Post, "video"):
        post.video = video

    try:
        post.save()
    except Exception as exc:
        if _is_ajax(request):
            return JsonResponse({"ok": False, "error": str(exc)}, status=500)

        messages.error(request, str(exc))
        return redirect("feed:feed_home")

    if _is_ajax(request):
        return JsonResponse(
            {
                "ok": True,
                "message": "Post updated successfully.",
                "post_id": post.id,
            }
        )

    messages.success(request, "Post updated successfully.")
    return redirect("feed:feed_home")


@login_required
@require_POST
def delete_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)

    if not _user_owns_post(post, request.user):
        raise PermissionDenied("You can only delete your own posts.")

    post.delete()

    if _is_ajax(request):
        return JsonResponse(
            {
                "ok": True,
                "message": "Post deleted successfully.",
            }
        )

    messages.success(request, "Post deleted successfully.")
    return redirect("feed:feed_home")


@login_required
@require_POST
def like_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)

    user_field = _author_field_for(PostLike)

    if not user_field:
        return JsonResponse(
            {"ok": False, "error": "PostLike model needs a user or author field."},
            status=500,
        )

    lookup = {
        "post": post,
        user_field: request.user,
    }

    existing_like = PostLike.objects.filter(**lookup).first()

    if existing_like:
        existing_like.delete()
        liked = False
    else:
        PostLike.objects.create(**lookup)
        liked = True

    return JsonResponse(
        {
            "ok": True,
            "liked": liked,
            "likes_count": _post_likes_count(post),
        }
    )


@login_required
@require_POST
def add_comment(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    text = request.POST.get("comment", "").strip() or request.POST.get("content", "").strip()

    if not text:
        return JsonResponse(
            {"ok": False, "error": "Comment cannot be empty."},
            status=400,
        )

    create_data = {
        "post": post,
    }

    author_field = _author_field_for(Comment)
    if author_field:
        create_data[author_field] = request.user

    content_field = _content_field_for(Comment)
    if content_field:
        create_data[content_field] = text

    try:
        comment = Comment.objects.create(**create_data)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=500)

    return JsonResponse(
        {
            "ok": True,
            "message": "Comment added.",
            "comment_id": comment.id,
            "comment": text,
            "author": request.user.get_full_name() or request.user.get_username(),
        }
    )


@login_required
@require_POST
def report_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    reason = request.POST.get("reason", "").strip()

    PostReport = getattr(models, "PostReport", None)

    if PostReport:
        create_data = {
            "post": post,
        }

        author_field = _author_field_for(PostReport)
        if author_field:
            create_data[author_field] = request.user

        if _field_exists(PostReport, "reason"):
            create_data["reason"] = reason

        try:
            PostReport.objects.create(**create_data)
        except Exception as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=500)

    return JsonResponse(
        {
            "ok": True,
            "message": "Report received. We will review this post.",
        }
    )