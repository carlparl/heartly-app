from django.conf import settings
from notifications.activity import (
    notify_post_comment,
    notify_post_like,
    notify_post_report,
    notify_story_reaction,
)
from profiles.moderation_evidence import capture_post_evidence
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from profiles.blocking import hidden_user_ids_for

from .forms import EditPostForm, PostForm, StoryForm
from .models import (
    Comment,
    CommentReaction,
    Post,
    PostLike,
    PostReport,
    PostSave,
    Story,
    StoryReaction,
    StoryView,
)


POSTS_PER_PAGE = 12
VALID_REACTIONS = {"like", "love", "funny", "cute", "support", "wow"}
STORY_REACTION_EMOJIS = {
    StoryReaction.REACTION_LOVE: "❤️",
    StoryReaction.REACTION_LAUGH: "😂",
    StoryReaction.REACTION_WOW: "😮",
}


def clean_reaction_type(value):
    value = (value or "love").strip().lower()
    return value if value in VALID_REACTIONS else "love"


def wants_json(request):
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
        or request.POST.get("_ajax") == "1"
    )


def json_error(message, status=400, **extra):
    data = {"ok": False, "message": message}
    data.update(extra)
    return JsonResponse(data, status=status)


def json_success(message="", **extra):
    data = {"ok": True, "message": message}
    data.update(extra)
    return JsonResponse(data)


def first_form_error(form):
    for field, errors in form.errors.items():
        for error in errors:
            if field == "__all__":
                return str(error)

            field_obj = form.fields.get(field)
            label = field_obj.label if field_obj and field_obj.label else field.replace("_", " ").title()
            return f"{label}: {error}"

    return "Please correct the form and try again."


def upload_exception_message(exc):
    message = "Upload failed. Check the file type, file size, and media storage setup."
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
    return username_for(user)


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
    target.display_name = username
    target.username = username
    target.username_label = ""
    target.avatar_url = avatar_url_for(user)
    target.avatar_initials = initials_for(username)
    return target


def decorate_comment(
    comment,
    viewer=None,
    *,
    hidden_ids=None,
):
    decorate_user_identity(comment, comment.user)

    if hidden_ids is None:
        hidden_ids = (
            hidden_user_ids_for(viewer)
            if viewer and viewer.is_authenticated
            else set()
        )

    # Keep the old multi-reaction summary hidden, but support the single
    # Instagram-style heart count used inside the comments sheet.
    comment.viewer_reaction = ""
    comment.reaction_counts = {}
    comment.reaction_total = comment.reactions.count()

    if viewer and viewer.is_authenticated:
        reaction = comment.reactions.filter(user=viewer).first()
        if reaction:
            comment.viewer_reaction = reaction.reaction_type

    replies_qs = comment.replies
    if hidden_ids:
        replies_qs = replies_qs.exclude(
            user_id__in=hidden_ids
        )

    replies = list(
        replies_qs
        .select_related("user", "user__profile")
        .order_by("created_at")[:4]
    )

    for reply in replies:
        decorate_comment(
            reply,
            viewer,
            hidden_ids=hidden_ids,
        )

    comment.visible_replies = replies
    visible_replies = comment.replies
    if hidden_ids:
        visible_replies = visible_replies.exclude(
            user_id__in=hidden_ids
        )
    comment.replies_count = visible_replies.count()
    comment.more_replies_count = max(comment.replies_count - len(replies), 0)
    return comment


def decorate_post(post, viewer):
    owner = post_owner(post)
    decorate_user_identity(post, owner)

    post.viewer_reaction = ""
    post.is_liked_by_user = False
    post.likes_count = post.likes.count()
    post.is_saved_by_user = False
    post.saves_count = post.saves.count()

    # Do not display the old multi-reaction summary.
    post.reaction_counts = {}

    if viewer and viewer.is_authenticated:
        reaction = post.likes.filter(user=viewer).first()
        if reaction:
            post.viewer_reaction = reaction.reaction_type
            post.is_liked_by_user = True

        post.is_saved_by_user = post.saves.filter(user=viewer).exists()

    hidden_ids = (
        hidden_user_ids_for(viewer)
        if viewer and viewer.is_authenticated
        else set()
    )
    visible_comments = post.comments.filter(
        parent__isnull=True
    )
    if hidden_ids:
        visible_comments = visible_comments.exclude(
            user_id__in=hidden_ids
        )

    post.comments_count = visible_comments.count()

    # Render enough comments for the bottom sheet without adding a new endpoint.
    # This keeps the first patch simple and fast for the current app size.
    visible_comments = list(
        visible_comments
        .select_related("user", "user__profile")
        .prefetch_related(
            "reactions",
            "replies",
            "replies__user",
            "replies__user__profile",
            "replies__reactions",
        )
        .order_by("-created_at")[:30]
    )
    visible_comments.reverse()

    for comment in visible_comments:
        decorate_comment(
            comment,
            viewer,
            hidden_ids=hidden_ids,
        )

    post.visible_comments = visible_comments
    post.more_comments_count = max(post.comments_count - len(visible_comments), 0)
    post.image_url = _safe_file_url(post.image)
    post.video_url = _safe_file_url(post.video)

    if post.image_url and post.avatar_url and post.image_url == post.avatar_url:
        post.image_url = ""

    return post


def enrich_posts(posts, viewer):
    for post in posts:
        yield decorate_post(post, viewer)


def visible_posts_for(viewer):
    queryset = Post.objects.filter(
        hidden_by_moderation=False,
    )
    hidden_ids = hidden_user_ids_for(viewer)

    if hidden_ids:
        queryset = queryset.exclude(author_id__in=hidden_ids)

    return queryset


def visible_active_stories(viewer):
    queryset = (
        Story.objects.active()
        .select_related("author", "author__profile")
        .order_by("-created_at")
    )

    hidden_ids = hidden_user_ids_for(viewer)
    if hidden_ids:
        queryset = queryset.exclude(author_id__in=hidden_ids)

    return queryset


def decorate_story(
    story,
    viewer=None,
    *,
    include_reactions=False,
):
    decorate_user_identity(story, story.author)
    story.media_url = _safe_file_url(
        story.video or story.image
    )
    story.viewer_reaction = ""
    story.reaction_counts = {
        reaction_type: 0
        for reaction_type
        in STORY_REACTION_EMOJIS
    }
    story.reaction_total = 0

    if include_reactions:
        rows = (
            story.reactions
            .values("reaction_type")
            .annotate(total=Count("id"))
        )

        for row in rows:
            reaction_type = row["reaction_type"]

            if (
                reaction_type
                in story.reaction_counts
            ):
                story.reaction_counts[
                    reaction_type
                ] = row["total"]

        story.reaction_total = sum(
            story.reaction_counts.values()
        )

        if (
            viewer is not None
            and viewer.is_authenticated
        ):
            reaction = (
                story.reactions
                .filter(user=viewer)
                .first()
            )

            if reaction is not None:
                story.viewer_reaction = (
                    reaction.reaction_type
                )

    return story


def story_groups_for(viewer):
    stories = list(visible_active_stories(viewer))
    seen_ids = set(
        StoryView.objects.filter(
            viewer=viewer,
            story_id__in=[story.id for story in stories],
        ).values_list("story_id", flat=True)
    )

    groups = {}
    order = []

    for story in stories:
        decorate_story(story)
        if story.author_id not in groups:
            groups[story.author_id] = {
                "author_id": story.author_id,
                "latest_story": story,
                "entry_story": story,
                "stories": [],
                "story_count": 0,
                "has_unseen": False,
                "is_owner": story.author_id == viewer.id,
            }
            order.append(story.author_id)

        group = groups[story.author_id]
        group["stories"].append(story)
        group["story_count"] += 1

        if (
            story.author_id != viewer.id
            and story.id not in seen_ids
        ):
            group["has_unseen"] = True

    order.sort(
        key=lambda author_id: (
            groups[author_id]["is_owner"],
            groups[author_id]["latest_story"].created_at,
        ),
        reverse=True,
    )

    ordered_groups = []

    for author_id in order:
        group = groups[author_id]
        group["stories"].sort(
            key=lambda item: (
                item.created_at,
                item.id,
            )
        )

        unseen_stories = [
            item
            for item in group["stories"]
            if (
                item.author_id == viewer.id
                or item.id not in seen_ids
            )
        ]

        group["entry_story"] = (
            unseen_stories[0]
            if unseen_stories
            else group["stories"][0]
        )
        ordered_groups.append(group)

    return ordered_groups


def story_playlist_for(viewer):
    playlist = []

    for group in story_groups_for(viewer):
        playlist.extend(group["stories"])

    return playlist


def render_post_card(request, post):
    post = decorate_post(post, request.user)
    return render_to_string(
        "feed/_post_card.html",
        {"post": post, "request": request},
        request=request,
    )


def render_comment_html(
    request,
    comment,
    *,
    is_reply=False,
):
    comment = decorate_comment(comment, request.user)
    return render_to_string(
        "feed/_comment_item.html",
        {
            "comment": comment,
            "request": request,
            "is_reply": is_reply,
        },
        request=request,
    )


def toggle_post_reaction(
    *,
    post,
    user,
    reaction_type,
):
    """
    Toggle one user's reaction inside a transaction.

    The retry handles two nearly simultaneous first reactions that
    race against the database uniqueness constraint.
    """
    for attempt in range(2):
        try:
            with transaction.atomic():
                reaction = (
                    PostLike.objects
                    .select_for_update()
                    .filter(
                        post=post,
                        user=user,
                    )
                    .first()
                )

                if reaction is None:
                    PostLike.objects.create(
                        post=post,
                        user=user,
                        reaction_type=reaction_type,
                    )
                    return True

                if reaction.reaction_type == reaction_type:
                    reaction.delete()
                    return False

                reaction.reaction_type = reaction_type
                reaction.save(
                    update_fields=["reaction_type"]
                )
                return True
        except IntegrityError:
            if attempt == 1:
                raise

    return False


def set_story_reaction(
    *,
    story,
    user,
    reaction_type,
):
    for attempt in range(2):
        try:
            with transaction.atomic():
                reaction = (
                    StoryReaction.objects
                    .select_for_update()
                    .filter(
                        story=story,
                        user=user,
                    )
                    .first()
                )

                if reaction is None:
                    reaction = (
                        StoryReaction.objects
                        .create(
                            story=story,
                            user=user,
                            reaction_type=(
                                reaction_type
                            ),
                        )
                    )
                    return reaction, True

                if (
                    reaction.reaction_type
                    == reaction_type
                ):
                    return reaction, False

                reaction.reaction_type = (
                    reaction_type
                )
                reaction.save(
                    update_fields=[
                        "reaction_type",
                        "updated_at",
                    ]
                )
                return reaction, True
        except IntegrityError:
            if attempt == 1:
                raise

    raise IntegrityError(
        "Story reaction could not be saved."
    )


def story_reaction_counts(story):
    counts = {
        reaction_type: 0
        for reaction_type
        in STORY_REACTION_EMOJIS
    }

    rows = (
        story.reactions
        .values("reaction_type")
        .annotate(total=Count("id"))
    )

    for row in rows:
        reaction_type = row["reaction_type"]

        if reaction_type in counts:
            counts[reaction_type] = row["total"]

    return counts


def toggle_saved_post(*, post, user):
    for attempt in range(2):
        try:
            with transaction.atomic():
                saved_item = (
                    PostSave.objects
                    .select_for_update()
                    .filter(
                        post=post,
                        user=user,
                    )
                    .first()
                )

                if saved_item is None:
                    PostSave.objects.create(
                        post=post,
                        user=user,
                    )
                    return True

                saved_item.delete()
                return False
        except IntegrityError:
            if attempt == 1:
                raise

    return False


def toggle_comment_reaction(
    *,
    comment,
    user,
    reaction_type,
):
    for attempt in range(2):
        try:
            with transaction.atomic():
                reaction = (
                    CommentReaction.objects
                    .select_for_update()
                    .filter(
                        comment=comment,
                        user=user,
                    )
                    .first()
                )

                if reaction is None:
                    CommentReaction.objects.create(
                        comment=comment,
                        user=user,
                        reaction_type=reaction_type,
                    )
                    return True

                if reaction.reaction_type == reaction_type:
                    reaction.delete()
                    return False

                reaction.reaction_type = reaction_type
                reaction.save(
                    update_fields=["reaction_type"]
                )
                return True
        except IntegrityError:
            if attempt == 1:
                raise

    return False


@login_required
def feed_home(request):
    posts_qs = (
        visible_posts_for(request.user)
        .select_related("author", "author__profile")
        .prefetch_related(
            "likes",
            "saves",
            Prefetch(
                "comments",
                queryset=Comment.objects.select_related("user", "user__profile").order_by("created_at"),
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
            "story_groups": story_groups_for(request.user),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def create_story(request):
    if request.method == "POST":
        form = StoryForm(request.POST, request.FILES)

        if form.is_valid():
            story = form.save(commit=False)
            story.author = request.user

            try:
                story.save()
            except Exception as exc:
                messages.error(request, upload_exception_message(exc))
            else:
                messages.success(request, "Story shared.")
                return redirect("feed:story_detail", story_id=story.id)
    else:
        form = StoryForm()

    return render(
        request,
        "feed/story_create.html",
        {"story_form": form},
    )


@login_required
@require_GET
def story_detail(request, story_id):
    story = get_object_or_404(
        visible_active_stories(request.user),
        id=story_id,
    )
    decorate_story(
        story,
        request.user,
        include_reactions=True,
    )

    if story.author_id != request.user.id:
        StoryView.objects.get_or_create(
            story=story,
            viewer=request.user,
        )

    story_playlist = story_playlist_for(
        request.user
    )
    story_ids = [
        playlist_story.id
        for playlist_story in story_playlist
    ]
    current_index = story_ids.index(story.id)

    previous_story_id = (
        story_ids[current_index - 1]
        if current_index > 0
        else None
    )
    next_story_id = (
        story_ids[current_index + 1]
        if current_index + 1 < len(story_ids)
        else None
    )
    story_position = current_index + 1
    story_total = len(story_ids)

    viewers = []
    if story.author_id == request.user.id:
        viewer_queryset = (
            story.views
            .exclude(viewer_id=request.user.id)
            .select_related("viewer", "viewer__profile")
            .order_by("-viewed_at")
        )
        hidden_viewer_ids = hidden_user_ids_for(request.user)
        if hidden_viewer_ids:
            viewer_queryset = viewer_queryset.exclude(
                viewer_id__in=hidden_viewer_ids
            )
        viewers = list(viewer_queryset)
        for view in viewers:
            decorate_user_identity(view, view.viewer)

    return render(
        request,
        "feed/story_detail.html",
        {
            "story": story,
            "previous_story_id": previous_story_id,
            "next_story_id": next_story_id,
            "story_position": story_position,
            "story_total": story_total,
            "story_viewers": viewers,
        },
    )


@login_required
@require_POST
def react_story(request, story_id):
    story = get_object_or_404(
        visible_active_stories(request.user),
        id=story_id,
    )

    if story.author_id == request.user.id:
        return json_error(
            "You cannot react to your own Story.",
            status=400,
        )

    reaction_type = (
        request.POST.get("reaction_type")
        or ""
    ).strip().lower()

    if (
        reaction_type
        not in STORY_REACTION_EMOJIS
    ):
        return json_error(
            "Choose a valid Story reaction.",
            status=400,
        )

    reaction, changed = set_story_reaction(
        story=story,
        user=request.user,
        reaction_type=reaction_type,
    )

    if changed:
        notify_story_reaction(
            story,
            request.user,
            emoji=STORY_REACTION_EMOJIS[
                reaction.reaction_type
            ],
        )

    counts = story_reaction_counts(story)

    if wants_json(request):
        return json_success(
            story_id=story.id,
            reaction_type=(
                reaction.reaction_type
            ),
            reaction_counts=counts,
            reaction_total=sum(
                counts.values()
            ),
            changed=changed,
        )

    return redirect(
        "feed:story_detail",
        story_id=story.id,
    )


@login_required
@require_POST
def delete_story(request, story_id):
    story = get_object_or_404(
        Story,
        id=story_id,
        author=request.user,
    )
    story.delete()
    messages.success(request, "Story deleted.")
    return redirect("feed:feed_home")


@login_required
@require_POST
def create_post(request):
    content = (request.POST.get("content") or "").strip()
    image = request.FILES.get("image")
    video = request.FILES.get("video")

    if image and video:
        return respond_error(request, "Please upload either an image or a video, not both.")

    if not content and not image and not video:
        return respond_error(request, "A post cannot be empty. Add text, an image, or a video.")

    form = PostForm(request.POST, request.FILES)

    if not form.is_valid():
        return respond_error(request, first_form_error(form))

    post = form.save(commit=False)
    post.author = request.user
    post.content = content
    post.image = image if image else None
    post.video = video if video else None

    try:
        post.save()
    except Exception as exc:
        return respond_error(request, upload_exception_message(exc), status=500)

    if wants_json(request):
        return json_success(post_id=post.id, post_html=render_post_card(request, post))

    messages.success(request, "Post shared.")
    return redirect("feed:feed_home")


@login_required
@require_POST
def edit_post(request, post_id):
    post = get_object_or_404(Post, id=post_id, author=request.user)

    image = request.FILES.get("image")
    video = request.FILES.get("video")
    remove_image = request.POST.get("remove_image") == "1" or request.POST.get("image-clear") == "on"
    remove_video = request.POST.get("remove_video") == "1" or request.POST.get("video-clear") == "on"

    if image and video:
        return respond_error(request, "Please upload either an image or a video, not both.")

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
        return respond_error(request, "A post cannot be empty. Add text, an image, or a video.")

    updated_post.edited_at = timezone.now()

    try:
        updated_post.save()
    except Exception as exc:
        return respond_error(request, upload_exception_message(exc), status=500)

    if wants_json(request):
        return json_success(post_id=updated_post.id, post_html=render_post_card(request, updated_post))

    messages.success(request, "Post updated.")
    return redirect("feed:feed_home")


@login_required
@require_POST
def delete_post(request, post_id):
    post = get_object_or_404(Post, id=post_id, author=request.user)
    post.delete()

    if wants_json(request):
        return json_success(post_id=post_id, remove_post_id=post_id)

    messages.success(request, "Post deleted.")
    return redirect("feed:feed_home")


@login_required
@require_POST
def like_post(request, post_id):
    post = get_object_or_404(
        visible_posts_for(request.user),
        id=post_id,
    )
    reaction_type = clean_reaction_type(request.POST.get("reaction_type"))

    reacted = toggle_post_reaction(
        post=post,
        user=request.user,
        reaction_type=reaction_type,
    )

    notify_post_like(
        post,
        request.user,
        reacted,
    )

    post = decorate_post(post, request.user)

    if wants_json(request):
        return json_success(
            post_id=post.id,
            reacted=reacted,
            reaction_type=reaction_type if reacted else "",
            likes_count=post.likes_count,
        )

    return redirect(request.POST.get("next") or reverse("feed:feed_home"))


@login_required
@require_POST
def save_post(request, post_id):
    post = get_object_or_404(
        visible_posts_for(request.user),
        id=post_id,
    )

    saved = toggle_saved_post(
        post=post,
        user=request.user,
    )

    post = decorate_post(post, request.user)

    if wants_json(request):
        return json_success(
            post_id=post.id,
            saved=saved,
            saves_count=post.saves_count,
        )

    return redirect(request.POST.get("next") or reverse("feed:feed_home"))


@login_required
@require_POST
def comment_post(request, post_id):
    post = get_object_or_404(
        visible_posts_for(request.user),
        id=post_id,
    )
    content = (request.POST.get("content") or request.POST.get("comment") or "").strip()

    if not content:
        return respond_error(request, "Comment cannot be empty.")

    parent = None
    parent_id = request.POST.get("parent_id")

    if parent_id:
        parent = get_object_or_404(Comment, id=parent_id, post=post, parent__isnull=True)

    with transaction.atomic():
        comment = Comment.objects.create(
            post=post,
            user=request.user,
            parent=parent,
            content=content,
        )
        transaction.on_commit(
            lambda item=comment: notify_post_comment(
                item
            ),
            robust=True,
        )

    post = decorate_post(post, request.user)

    if wants_json(request):
        return json_success(
            post_id=post.id,
            comment_id=comment.id,
            parent_id=parent.id if parent else None,
            comments_count=post.comments_count,
            comment_html=render_comment_html(
                request,
                comment,
                is_reply=bool(parent),
            ),
        )

    return redirect("feed:feed_home")


@login_required
@require_POST
def reply_comment(request, comment_id):
    parent = get_object_or_404(
        Comment.objects.filter(
            post__in=visible_posts_for(request.user),
        ),
        id=comment_id,
        parent__isnull=True,
    )
    post = parent.post
    content = (request.POST.get("content") or request.POST.get("reply") or "").strip()

    if not content:
        return respond_error(request, "Reply cannot be empty.")

    with transaction.atomic():
        reply = Comment.objects.create(
            post=post,
            user=request.user,
            parent=parent,
            content=content,
        )
        transaction.on_commit(
            lambda item=reply: notify_post_comment(
                item
            ),
            robust=True,
        )

    post = decorate_post(post, request.user)
    replies_count = parent.replies.count()

    if wants_json(request):
        return json_success(
            post_id=post.id,
            comment_id=parent.id,
            parent_id=parent.id,
            reply_id=reply.id,
            replies_count=replies_count,
            comments_count=post.comments_count,
            reply_html=render_comment_html(
                request,
                reply,
                is_reply=True,
            ),
        )

    return redirect("feed:feed_home")


@login_required
@require_POST
def react_comment(request, comment_id):
    # Kept for URL compatibility. The rebuilt templates no longer display
    # comment reaction controls.
    comment = get_object_or_404(
        Comment.objects.filter(
            post__in=visible_posts_for(request.user),
        ),
        id=comment_id,
    )
    reaction_type = clean_reaction_type(request.POST.get("reaction_type"))

    reacted = toggle_comment_reaction(
        comment=comment,
        user=request.user,
        reaction_type=reaction_type,
    )
    reaction_count = comment.reactions.count()
    post = comment.post

    if wants_json(request):
        return json_success(
            post_id=post.id,
            comment_id=comment.id,
            reacted=reacted,
            reaction_type=reaction_type if reacted else "",
            reaction_count=reaction_count,
        )

    return redirect("feed:feed_home")


@login_required
@require_POST
def report_post(request, post_id):
    post = get_object_or_404(
        visible_posts_for(request.user),
        id=post_id,
    )

    if post.author_id == request.user.id:
        return respond_error(request, "You cannot report your own post.")

    reason = (
        request.POST.get("reason")
        or PostReport.REASON_OTHER
    ).strip()
    valid_reasons = {
        value for value, _label in PostReport.REASON_CHOICES
    }
    if reason not in valid_reasons:
        reason = PostReport.REASON_OTHER

    details = (
        request.POST.get("details") or ""
    ).strip()[:2000]
    report, created = PostReport.objects.get_or_create(
        post=post,
        reporter=request.user,
        defaults={
            "reason": reason,
            "details": details,
            "evidence_snapshot": capture_post_evidence(post),
        },
    )

    if created:
        notify_post_report(report)

    if wants_json(request):
        return json_success(
            post_id=post.id,
            report_id=report.id,
            created=created,
        )

    if not created:
        messages.info(request, "You already reported this post.")
        return redirect("feed:feed_home")

    messages.success(request, "Post reported. Our team will review it.")
    return redirect("feed:feed_home")
