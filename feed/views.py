try:
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
except Exception:
    async_to_sync = None
    get_channel_layer = None

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Comment, Post, PostLike, PostReport

try:
    from profiles.blocking import hidden_user_ids_for
except Exception:
    hidden_user_ids_for = None

try:
    from notifications.models import Notification
except Exception:
    Notification = None


User = get_user_model()


def is_ajax(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def ajax_or_redirect(request, data, redirect_to="feed:feed_home", status=200):
    if is_ajax(request):
        return JsonResponse(data, status=status)
    return redirect(redirect_to)


def back_to_feed(request):
    return request.META.get("HTTP_REFERER") or reverse("feed:feed_home")


def model_has_field(model, field_name):
    return any(field.name == field_name for field in model._meta.fields)


def get_profile_safe(user):
    """
    Read the existing profile without creating one.
    This avoids like/comment actions failing just because the profile table or
    profile fields are not ready on the deployed database.
    """
    for attr_name in ("profile", "userprofile"):
        try:
            profile = getattr(user, attr_name, None)
            if profile:
                return profile
        except Exception:
            continue
    return None


def get_display_name(user):
    profile = get_profile_safe(user)

    for field_name in ("display_name", "name", "full_name"):
        value = getattr(profile, field_name, "") if profile else ""
        if value:
            return value

    return user.get_full_name() or user.username or "User"


def get_profile_photo_url(user):
    profile = get_profile_safe(user)

    if not profile:
        return ""

    for field_name in ("profile_picture", "photo", "avatar", "image"):
        try:
            image_field = getattr(profile, field_name, None)
            if image_field:
                return image_field.url
        except Exception:
            continue

    return ""


def feed_post_url(post):
    return reverse("feed:feed_home") + f"?post={post.id}#post-{post.id}"


def notification_type(name, fallback):
    if Notification is None:
        return fallback
    return getattr(Notification, name, fallback)


def create_notification_safe(
    *,
    recipient,
    actor,
    notification_type,
    title,
    message,
    url,
    related_object_type,
    related_object_id,
):
    if Notification is None or recipient == actor:
        return None

    data = {
        "recipient": recipient,
        "actor": actor,
        "notification_type": notification_type,
        "title": title,
        "message": message,
        "url": url,
        "related_object_type": related_object_type,
        "related_object_id": related_object_id,
    }

    allowed_data = {
        key: value
        for key, value in data.items()
        if model_has_field(Notification, key)
    }

    try:
        return Notification.objects.create(**allowed_data)
    except Exception:
        return None


def send_live_feed_notification(
    *,
    recipient,
    actor,
    notification_type,
    title,
    message,
    url,
    post_id,
):
    if async_to_sync is None or get_channel_layer is None:
        return

    try:
        channel_layer = get_channel_layer()
    except Exception:
        return

    if not channel_layer:
        return

    try:
        async_to_sync(channel_layer.group_send)(
            f"heartly_user_{recipient.id}",
            {
                "type": "notification.event",
                "payload": {
                    "type": "feed_notification",
                    "notification_type": notification_type,
                    "title": title,
                    "message": message,
                    "actor_id": actor.id,
                    "actor_name": get_display_name(actor),
                    "actor_photo": get_profile_photo_url(actor),
                    "url": url,
                    "post_id": post_id,
                },
            },
        )
    except Exception:
        return


def notify_post_owner(post, actor, notification_type_value, title, message):
    if post.user_id == actor.id:
        return

    url = feed_post_url(post)

    notification = create_notification_safe(
        recipient=post.user,
        actor=actor,
        notification_type=notification_type_value,
        title=title,
        message=message,
        url=url,
        related_object_type="feed.post",
        related_object_id=post.id,
    )

    if notification:
        send_live_feed_notification(
            recipient=post.user,
            actor=actor,
            notification_type=notification_type_value,
            title=title,
            message=message,
            url=url,
            post_id=post.id,
        )


def notify_staff_about_report(post, reporter, report):
    try:
        staff_users = User.objects.filter(is_staff=True, is_active=True).exclude(id=reporter.id)
    except Exception:
        return

    for staff_user in staff_users:
        url = reverse("feed:feed_home") + f"?report={report.id}#post-{post.id}"
        type_value = notification_type("TYPE_REPORT", "report")

        notification = create_notification_safe(
            recipient=staff_user,
            actor=reporter,
            notification_type=type_value,
            title="Post report",
            message=f"{get_display_name(reporter)} reported a post.",
            url=url,
            related_object_type="feed.postreport",
            related_object_id=report.id,
        )

        if notification:
            send_live_feed_notification(
                recipient=staff_user,
                actor=reporter,
                notification_type=type_value,
                title="Post report",
                message=f"{get_display_name(reporter)} reported a post.",
                url=url,
                post_id=post.id,
            )


def attach_feed_display_data(posts, request_user):
    for post in posts:
        try:
            liked = post.likes.filter(user=request_user).exists()
        except Exception:
            liked = False

        post.is_liked = liked
        post.is_liked_by_user = liked
        post.author_name = get_display_name(post.user)
        post.author_photo = get_profile_photo_url(post.user)

        try:
            comments = post.comments.all()
        except Exception:
            comments = []

        for comment in comments:
            comment.author_name = get_display_name(comment.user)
            comment.author_photo = get_profile_photo_url(comment.user)

    return posts


@login_required
def feed_home(request):
    query = request.GET.get("q", "").strip()

    posts = (
        Post.objects
        .select_related("user")
        .prefetch_related("likes", "comments__user")
        .filter(is_hidden=False, hidden_by_moderation=False)
        .order_by("-created_at")
    )

    if hidden_user_ids_for:
        try:
            hidden_ids = hidden_user_ids_for(request.user)
        except Exception:
            hidden_ids = set()

        if hidden_ids:
            posts = posts.exclude(user_id__in=hidden_ids)

    if query:
        posts = posts.filter(
            Q(content__icontains=query)
            | Q(user__username__icontains=query)
            | Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
        )

    posts = list(posts)
    attach_feed_display_data(posts, request.user)

    return render(
        request,
        "feed/feed.html",
        {
            "posts": posts,
            "request_user_name": get_display_name(request.user),
            "request_user_photo": get_profile_photo_url(request.user),
            "focus_post_id": request.GET.get("post"),
            "search_query": query,
        },
    )


@login_required
@require_POST
def create_post(request):
    content = request.POST.get("content", "").strip()
    image = request.FILES.get("image")
    video = request.FILES.get("video")

    if image and video:
        data = {"success": False, "error": "Choose either a photo or a video, not both."}
        if is_ajax(request):
            return JsonResponse(data, status=400)
        messages.error(request, data["error"])
        return redirect("feed:feed_home")

    if not content and not image and not video:
        data = {"success": False, "error": "Write something or add media before posting."}
        if is_ajax(request):
            return JsonResponse(data, status=400)
        messages.error(request, data["error"])
        return redirect("feed:feed_home")

    post = Post.objects.create(
        user=request.user,
        content=content,
        image=image,
        video=video,
    )

    if is_ajax(request):
        return JsonResponse({"success": True, "post_id": post.id})

    messages.success(request, "Post created.")
    return redirect("feed:feed_home")


@login_required
@require_POST
def edit_post(request, post_id):
    post = get_object_or_404(Post, id=post_id, user=request.user)

    content = request.POST.get("content", "").strip()
    image = request.FILES.get("image")
    video = request.FILES.get("video")
    remove_media = request.POST.get("remove_media") == "on"

    if image and video:
        data = {"success": False, "error": "Choose either a photo or video, not both."}
        if is_ajax(request):
            return JsonResponse(data, status=400)
        messages.error(request, data["error"])
        return redirect("feed:feed_home")

    post.content = content

    if remove_media:
        if post.image:
            post.image.delete(save=False)
        if post.video:
            post.video.delete(save=False)
        post.image = None
        post.video = None

    if image:
        if post.image:
            post.image.delete(save=False)
        if post.video:
            post.video.delete(save=False)
        post.image = image
        post.video = None

    if video:
        if post.image:
            post.image.delete(save=False)
        if post.video:
            post.video.delete(save=False)
        post.video = video
        post.image = None

    if not post.content and not post.image and not post.video:
        data = {"success": False, "error": "A post cannot be empty."}
        if is_ajax(request):
            return JsonResponse(data, status=400)
        messages.error(request, data["error"])
        return redirect("feed:feed_home")

    post.edited_at = timezone.now()
    post.save()

    if is_ajax(request):
        return JsonResponse({"success": True, "post_id": post.id, "content": post.content})

    messages.success(request, "Post updated.")
    return redirect("feed:feed_home")


@login_required
@require_POST
def delete_post(request, post_id):
    post = get_object_or_404(Post, id=post_id, user=request.user)

    if post.image:
        post.image.delete(save=False)
    if post.video:
        post.video.delete(save=False)

    post.delete()

    if is_ajax(request):
        return JsonResponse({"success": True, "post_id": post_id})

    messages.success(request, "Post deleted.")
    return redirect("feed:feed_home")


@login_required
@require_POST
def toggle_like(request, post_id):
    post = get_object_or_404(Post.objects.select_related("user"), id=post_id)

    try:
        with transaction.atomic():
            like, created = PostLike.objects.get_or_create(
                post=post,
                user=request.user,
            )

            if created:
                liked = True
            else:
                like.delete()
                liked = False
    except IntegrityError:
        # Handles a rare double-click race condition safely.
        PostLike.objects.filter(post=post, user=request.user).delete()
        liked = False

    likes_count = PostLike.objects.filter(post=post).count()

    if liked:
        notify_post_owner(
            post=post,
            actor=request.user,
            notification_type_value=notification_type("TYPE_LIKE", "like"),
            title="New like",
            message=f"{get_display_name(request.user)} liked your post.",
        )

    if is_ajax(request):
        return JsonResponse(
            {
                "success": True,
                "liked": liked,
                "likes_count": likes_count,
                "total_likes": likes_count,
            }
        )

    return redirect(back_to_feed(request))


@login_required
@require_POST
def like_post(request, post_id):
    return toggle_like(request, post_id)


@login_required
@require_POST
def add_comment(request, post_id):
    post = get_object_or_404(Post.objects.select_related("user"), id=post_id)

    content = (
        request.POST.get("content", "").strip()
        or request.POST.get("text", "").strip()
    )

    if not content:
        data = {"success": False, "error": "Comment cannot be empty."}
        if is_ajax(request):
            return JsonResponse(data, status=400)
        messages.error(request, data["error"])
        return redirect(back_to_feed(request))

    # Match the frontend maxlength to avoid oversized accidental payloads.
    content = content[:600]

    comment = Comment.objects.create(
        post=post,
        user=request.user,
        content=content,
    )

    comments_count = Comment.objects.filter(post=post).count()

    notify_post_owner(
        post=post,
        actor=request.user,
        notification_type_value=notification_type("TYPE_COMMENT", "comment"),
        title="New comment",
        message=f"{get_display_name(request.user)} commented on your post.",
    )

    if is_ajax(request):
        return JsonResponse(
            {
                "success": True,
                "comment_id": comment.id,
                "comment": {
                    "id": comment.id,
                    "user": get_display_name(request.user),
                    "content": comment.content,
                    "text": comment.content,
                    "photo_url": get_profile_photo_url(request.user),
                    "photo_version": int(timezone.now().timestamp()),
                },
                "comments_count": comments_count,
                "total_comments": comments_count,
            }
        )

    messages.success(request, "Comment added.")
    return redirect(back_to_feed(request))


@login_required
@require_POST
def report_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)

    if post.user_id == request.user.id:
        data = {"success": False, "error": "You cannot report your own post."}
        if is_ajax(request):
            return JsonResponse(data, status=400)
        messages.error(request, data["error"])
        return redirect("feed:feed_home")

    reason = request.POST.get("reason", "other").strip() or "other"
    details = request.POST.get("details", "").strip()
    valid_reasons = [choice[0] for choice in PostReport.REASON_CHOICES]

    if reason not in valid_reasons:
        reason = "other"

    report, created = PostReport.objects.get_or_create(
        post=post,
        reporter=request.user,
        defaults={"reason": reason, "details": details},
    )

    if not created:
        report.reason = reason
        report.details = details
        report.reviewed = False
        report.status = PostReport.STATUS_PENDING
        report.save(update_fields=["reason", "details", "reviewed", "status"])

    notify_staff_about_report(post=post, reporter=request.user, report=report)

    if is_ajax(request):
        return JsonResponse({"success": True, "message": "Post reported."})

    messages.success(request, "Post reported.")
    return redirect("feed:feed_home")
