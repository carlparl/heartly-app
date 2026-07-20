from django.utils import timezone

from .models import Profile


EVIDENCE_SCHEMA_VERSION = 1
MAX_PROFILE_TEXT = 2000
MAX_POST_TEXT = 4000
MAX_MESSAGE_TEXT = 1200
MAX_CHAT_MESSAGES = 20


def _text(value, limit):
    return (value or "").strip()[:limit]


def _base_snapshot(kind):
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "kind": kind,
        "captured_at": timezone.now().isoformat(),
    }


def capture_profile_evidence(reported_user):
    snapshot = _base_snapshot("profile")
    profile = Profile.objects.filter(
        user_id=reported_user.id
    ).first()
    snapshot.update(
        {
            "reported_user_id": reported_user.id,
            "username": _text(reported_user.username, 150),
            "display_name": _text(
                getattr(profile, "display_name", ""),
                120,
            ),
            "bio": _text(
                getattr(profile, "bio", ""),
                MAX_PROFILE_TEXT,
            ),
            "location": _text(
                getattr(profile, "location", ""),
                120,
            ),
            "photo_count": (
                profile.photos.count() if profile else 0
            ),
        }
    )
    return snapshot


def capture_post_evidence(post):
    snapshot = _base_snapshot("post")
    media_types = []
    if post.image:
        media_types.append("image")
    if post.video:
        media_types.append("video")
    snapshot.update(
        {
            "post_id": post.id,
            "author_id": post.author_id,
            "content": _text(post.content, MAX_POST_TEXT),
            "media_types": media_types,
            "created_at": post.created_at.isoformat(),
            "edited_at": (
                post.edited_at.isoformat()
                if post.edited_at
                else None
            ),
        }
    )
    return snapshot


def capture_chat_evidence(thread, reported_user):
    snapshot = _base_snapshot("chat")
    messages = list(
        thread.messages.prefetch_related("attachments")
        .order_by("-created_at", "-id")[:MAX_CHAT_MESSAGES]
    )
    messages.reverse()
    snapshot.update(
        {
            "thread_id": thread.id,
            "reported_user_id": reported_user.id,
            "messages": [
                {
                    "message_id": message.id,
                    "sender_id": message.sender_id,
                    "text": _text(
                        message.text,
                        MAX_MESSAGE_TEXT,
                    ),
                    "created_at": message.created_at.isoformat(),
                    "attachments": [
                        {
                            "type": attachment.attachment_type,
                            "content_type": _text(
                                attachment.content_type,
                                120,
                            ),
                            "original_filename": _text(
                                attachment.original_filename,
                                255,
                            ),
                            "file_size": attachment.file_size,
                            "duration_seconds": (
                                attachment.duration_seconds
                            ),
                        }
                        for attachment in message.attachments.all()
                    ],
                }
                for message in messages
            ],
        }
    )
    return snapshot
