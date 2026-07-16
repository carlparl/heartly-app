from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import Notification
from .services import notify, notify_once


def display_name_for(user):
    if user is None:
        return "A Heartly member"
    profile = getattr(user, "profile", None)
    value = getattr(profile, "display_name", "") if profile is not None else ""
    if str(value or "").strip():
        return str(value).strip()
    full_name = str(user.get_full_name() or "").strip()
    if full_name:
        return full_name
    username = str(getattr(user, "username", "") or "").strip()
    if username:
        return username
    email = str(getattr(user, "email", "") or "").strip()
    if email:
        return email.split("@", 1)[0]
    return "A Heartly member"


def notify_post_like(post, actor, active):
    if post is None or actor is None:
        return None
    lookup = {
        "recipient_id": post.author_id,
        "actor": actor,
        "notification_type": Notification.TYPE_LIKE,
        "related_object_type": "feed.post",
        "related_object_id": post.id,
    }
    if not active:
        Notification.objects.filter(**lookup).delete()
        return None
    return notify_once(
        recipient=post.author,
        actor=actor,
        notification_type=Notification.TYPE_LIKE,
        title=f"{display_name_for(actor)} liked your post"[:120],
        message="Tap to view your post.",
        url=reverse("feed:feed_home"),
        related_object_type="feed.post",
        related_object_id=post.id,
    )


def notify_post_comment(comment):
    if comment is None:
        return []
    actor = comment.user
    post = comment.post
    created = []
    if comment.parent_id:
        parent_author = comment.parent.user
        item = notify(
            recipient=parent_author,
            actor=actor,
            notification_type=Notification.TYPE_COMMENT,
            title=f"{display_name_for(actor)} replied to your comment"[:120],
            message=(comment.content or "")[:240],
            url=reverse("feed:feed_home"),
            related_object_type="feed.comment_reply",
            related_object_id=comment.id,
        )
        if item is not None:
            created.append(item)
        if post.author_id not in {actor.id, parent_author.id}:
            item = notify(
                recipient=post.author,
                actor=actor,
                notification_type=Notification.TYPE_COMMENT,
                title=f"{display_name_for(actor)} replied on your post"[:120],
                message=(comment.content or "")[:240],
                url=reverse("feed:feed_home"),
                related_object_type="feed.comment_reply",
                related_object_id=comment.id,
            )
            if item is not None:
                created.append(item)
        return created
    item = notify(
        recipient=post.author,
        actor=actor,
        notification_type=Notification.TYPE_COMMENT,
        title=f"{display_name_for(actor)} commented on your post"[:120],
        message=(comment.content or "")[:240],
        url=reverse("feed:feed_home"),
        related_object_type="feed.comment",
        related_object_id=comment.id,
    )
    if item is not None:
        created.append(item)
    return created


def notify_profile_like(actor, recipient, *, active):
    if actor is None or recipient is None or actor.pk == recipient.pk:
        return None
    lookup = {
        "recipient": recipient,
        "actor": actor,
        "notification_type": Notification.TYPE_LIKE,
        "related_object_type": "matches.profile_like",
        "related_object_id": actor.id,
    }
    if not active:
        Notification.objects.filter(**lookup).delete()
        return None
    return notify_once(
        recipient=recipient,
        actor=actor,
        notification_type=Notification.TYPE_LIKE,
        title="New profile like",
        message=f"{display_name_for(actor)} liked your profile.",
        url=reverse("matches:discover"),
        related_object_type="matches.profile_like",
        related_object_id=actor.id,
    )


def clear_profile_like_notifications(user_a, user_b):
    deleted_a, _ = Notification.objects.filter(
        recipient=user_a,
        actor=user_b,
        notification_type=Notification.TYPE_LIKE,
        related_object_type="matches.profile_like",
        related_object_id=user_b.id,
    ).delete()
    deleted_b, _ = Notification.objects.filter(
        recipient=user_b,
        actor=user_a,
        notification_type=Notification.TYPE_LIKE,
        related_object_type="matches.profile_like",
        related_object_id=user_a.id,
    ).delete()
    return deleted_a + deleted_b


def notify_mutual_match(match, user_a, user_b):
    if match is None:
        return []
    clear_profile_like_notifications(user_a, user_b)
    first = notify_once(
        recipient=user_a,
        actor=user_b,
        notification_type=Notification.TYPE_MATCH,
        title="New match",
        message=f"You and {display_name_for(user_b)} matched. Start chatting now.",
        url=reverse("matches:your_matches"),
        related_object_type="matches.mutualmatch",
        related_object_id=match.id,
    )
    second = notify_once(
        recipient=user_b,
        actor=user_a,
        notification_type=Notification.TYPE_MATCH,
        title="New match",
        message=f"You and {display_name_for(user_a)} matched. Start chatting now.",
        url=reverse("matches:your_matches"),
        related_object_type="matches.mutualmatch",
        related_object_id=match.id,
    )
    return [item for item in (first, second) if item is not None]


def notify_chat_message(message):
    if message is None:
        return None
    recipient = message.thread.other_user(message.sender)
    return notify(
        recipient=recipient,
        actor=message.sender,
        notification_type=Notification.TYPE_MESSAGE,
        title="New message",
        message=f"{display_name_for(message.sender)} sent you a message.",
        url=reverse("chat:chat_room", args=[message.thread_id]),
        related_object_type="chat.chatmessage",
        related_object_id=message.id,
    )


def mark_thread_message_notifications_read(thread, user):
    message_ids = thread.messages.exclude(sender=user).values_list("id", flat=True)
    return Notification.objects.filter(
        recipient=user,
        notification_type=Notification.TYPE_MESSAGE,
        related_object_type="chat.chatmessage",
        related_object_id__in=message_ids,
        is_read=False,
    ).update(is_read=True)


def notify_chat_report(report):
    if report is None:
        return []
    User = get_user_model()
    created = []
    for staff_user in User.objects.filter(is_active=True, is_staff=True).exclude(id=report.reporter_id):
        item = notify_once(
            recipient=staff_user,
            actor=report.reporter,
            notification_type=Notification.TYPE_REPORT,
            title="Chat report",
            message=f"{display_name_for(report.reporter)} reported a chat.",
            url=reverse("chat:chat_room", args=[report.thread_id]),
            related_object_type="chat.chatreport",
            related_object_id=report.id,
        )
        if item is not None:
            created.append(item)
    return created
