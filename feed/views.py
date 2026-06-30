from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Comment, Post, PostLike, PostMedia


ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"]
ALLOWED_VIDEO_TYPES = ["video/mp4", "video/webm", "video/quicktime"]

MAX_IMAGES_PER_POST = 4

MAX_IMAGE_SIZE = 5 * 1024 * 1024
MAX_VIDEO_SIZE = 50 * 1024 * 1024


def get_profile_photo_url(user):
    try:
        profile = getattr(user, "profile", None)

        if profile and getattr(profile, "profile_picture", None):
            return profile.profile_picture.url
    except Exception:
        pass

    return static("images/default-avatar.png")


def get_uploaded_images(request):
    """
    X-style image uploads:
    - Main field: images
    - Fallback field: image, for older templates
    """

    images = request.FILES.getlist("images")

    if not images:
        single_image = request.FILES.get("image")
        if single_image:
            images = [single_image]

    return images


def get_uploaded_video(request):
    """
    X-style video upload:
    - Only one video per post.
    """

    return request.FILES.get("video")


def validate_media_upload(images, video):
    """
    X-style rules:
    - Max 4 images.
    - OR 1 video.
    - Images and video cannot be mixed.
    """

    if images and video:
        return False, "Upload either images or one video, not both."

    if len(images) > MAX_IMAGES_PER_POST:
        return False, "You can upload up to 4 images."

    for image in images:
        if image.content_type not in ALLOWED_IMAGE_TYPES:
            return False, "Only JPG, PNG, and WEBP images are allowed."

        if image.size > MAX_IMAGE_SIZE:
            return False, "Each image must be 5MB or smaller."

    if video:
        if video.content_type not in ALLOWED_VIDEO_TYPES:
            return False, "Only MP4, WEBM, and MOV videos are allowed."

        if video.size > MAX_VIDEO_SIZE:
            return False, "Video must be 50MB or smaller."

    return True, None


def create_post_media(post, images, video, alt_texts=None):
    alt_texts = alt_texts or []

    if images:
        for index, image in enumerate(images):
            alt_text = ""

            if index < len(alt_texts):
                alt_text = alt_texts[index].strip()

            PostMedia.objects.create(
                post=post,
                media_type=PostMedia.IMAGE,
                image=image,
                alt_text=alt_text,
                order=index,
            )

    if video:
        PostMedia.objects.create(
            post=post,
            media_type=PostMedia.VIDEO,
            video=video,
            order=0,
        )


@login_required
def feed_home(request):
    posts = (
        Post.objects
        .select_related("user")
        .prefetch_related("media", "likes", "comments__user")
        .all()[:50]
    )

    posts_data = []

    for post in posts:
        posts_data.append(
            {
                "post": post,
                "author_name": post.user.get_full_name() or post.user.username,
                "author_photo": get_profile_photo_url(post.user),
                "media": post.media.all(),
                "likes_count": post.likes.count(),
                "comments_count": post.comments.count(),
                "is_liked": post.likes.filter(user=request.user).exists(),
                "comments": post.comments.select_related("user").all()[:3],
            }
        )

    return render(
        request,
        "feed/feed.html",
        {
            "posts_data": posts_data,
        },
    )


@login_required
@require_POST
def create_post(request):
    content = request.POST.get("content", "").strip()

    images = get_uploaded_images(request)
    video = get_uploaded_video(request)

    alt_texts = request.POST.getlist("image_alt_texts")

    is_valid, error_message = validate_media_upload(images, video)

    if not is_valid:
        messages.error(request, error_message)
        return redirect("feed:feed_home")

    if not content and not images and not video:
        messages.error(request, "Write something or add media before posting.")
        return redirect("feed:feed_home")

    post = Post.objects.create(
        user=request.user,
        content=content,
    )

    create_post_media(
        post=post,
        images=images,
        video=video,
        alt_texts=alt_texts,
    )

    messages.success(request, "Post created.")
    return redirect("feed:feed_home")


@login_required
@require_POST
def edit_post(request, post_id):
    post = get_object_or_404(Post, id=post_id, user=request.user)

    content = request.POST.get("content", "").strip()

    images = get_uploaded_images(request)
    video = get_uploaded_video(request)

    alt_texts = request.POST.getlist("image_alt_texts")

    remove_media = request.POST.get("remove_media") == "on"
    replace_media = bool(images or video)

    is_valid, error_message = validate_media_upload(images, video)

    if not is_valid:
        messages.error(request, error_message)
        return redirect("feed:feed_home")

    has_existing_media = post.media.exists()

    if not content and not has_existing_media and not replace_media:
        messages.error(request, "A post cannot be empty.")
        return redirect("feed:feed_home")

    if not content and remove_media and not replace_media:
        messages.error(request, "A post cannot be empty.")
        return redirect("feed:feed_home")

    post.content = content
    post.edited_at = timezone.now()
    post.save()

    if remove_media or replace_media:
        post.media.all().delete()

    if replace_media:
        create_post_media(
            post=post,
            images=images,
            video=video,
            alt_texts=alt_texts,
        )

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

    like, created = PostLike.objects.get_or_create(
        post=post,
        user=request.user,
    )

    if not created:
        like.delete()

    return redirect("feed:feed_home")


@login_required
@require_POST
def add_comment(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    text = request.POST.get("text", "").strip()

    if not text:
        messages.error(request, "Comment cannot be empty.")
        return redirect("feed:feed_home")

    Comment.objects.create(
        post=post,
        user=request.user,
        text=text,
    )

    return redirect("feed:feed_home")