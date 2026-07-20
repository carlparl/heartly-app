from datetime import date, datetime

from allauth.account.models import EmailAddress
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from ai_features.models import HeartlyMessage
from chat.models import (
    Call,
    CallSession,
    ChatAttachment,
    ChatMessage,
    ChatReport,
)
from feed.models import (
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
from matches.models import MatchAction, MutualMatch
from notifications.models import Notification, PushSubscription
from profiles.models import Profile, ProfileReport, UserBlock


EXPORT_SCHEMA_VERSION = 1


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _records(queryset, fields, *, limit):
    rows = list(
        queryset.order_by("pk").values(*fields)[: limit + 1]
    )
    truncated = len(rows) > limit
    rows = rows[:limit]
    return {
        "records": [
            {key: _json_value(value) for key, value in row.items()}
            for row in rows
        ],
        "truncated": truncated,
    }


def _mutual_matches(user, *, limit):
    rows = list(
        MutualMatch.objects
        .filter(Q(user_one=user) | Q(user_two=user))
        .order_by("pk")[: limit + 1]
    )
    truncated = len(rows) > limit
    return {
        "records": [
            {
                "id": match.id,
                "other_user_id": (
                    match.user_two_id
                    if match.user_one_id == user.id
                    else match.user_one_id
                ),
                "created_at": match.created_at.isoformat(),
            }
            for match in rows[:limit]
        ],
        "truncated": truncated,
    }


def build_user_data_export(user):
    """Build a bounded export without internal evidence or staff notes."""
    limit = settings.HEARTLY_DATA_EXPORT_MAX_RECORDS
    profile = Profile.objects.filter(user=user).first()
    profile_data = None
    interests = []
    photos = {"records": [], "truncated": False}
    if profile:
        profile_data = {
            "display_name": profile.display_name,
            "age": profile.age,
            "location": profile.location,
            "bio": profile.bio,
            "gender": profile.gender,
            "interested_in": profile.interested_in,
            "connection_goal": profile.connection_goal,
            "email_verified": profile.email_verified,
            "profile_visible": profile.profile_visible,
            "show_online_status": profile.show_online_status,
            "allow_message_requests": profile.allow_message_requests,
            "safety_filters_enabled": profile.safety_filters_enabled,
            "created_at": profile.created_at.isoformat(),
            "updated_at": profile.updated_at.isoformat(),
        }
        interests = list(
            profile.interests.order_by("name").values_list(
                "name", flat=True
            )[:limit]
        )
        photos = _records(
            profile.photos.all(),
            ("id", "image", "position", "created_at", "updated_at"),
            limit=limit,
        )

    collections = {
        "email_addresses": _records(
            EmailAddress.objects.filter(user=user),
            ("id", "email", "verified", "primary"),
            limit=limit,
        ),
        "profile_photos": photos,
        "blocks_created": _records(
            UserBlock.objects.filter(blocker=user),
            ("id", "blocked_id", "created_at"),
            limit=limit,
        ),
        "match_actions_sent": _records(
            MatchAction.objects.filter(from_user=user),
            ("id", "to_user_id", "action", "created_at"),
            limit=limit,
        ),
        "mutual_matches": _mutual_matches(user, limit=limit),
        "posts": _records(
            Post.objects.filter(author=user),
            (
                "id", "content", "image", "video", "created_at",
                "updated_at", "hidden_by_moderation",
            ),
            limit=limit,
        ),
        "comments": _records(
            Comment.objects.filter(user=user),
            ("id", "post_id", "parent_id", "content", "created_at"),
            limit=limit,
        ),
        "post_reactions": _records(
            PostLike.objects.filter(user=user),
            ("id", "post_id", "reaction_type", "created_at"),
            limit=limit,
        ),
        "saved_posts": _records(
            PostSave.objects.filter(user=user),
            ("id", "post_id", "created_at"),
            limit=limit,
        ),
        "comment_reactions": _records(
            CommentReaction.objects.filter(user=user),
            ("id", "comment_id", "reaction_type", "created_at"),
            limit=limit,
        ),
        "stories": _records(
            Story.objects.filter(author=user),
            (
                "id", "caption", "image", "video", "created_at",
                "expires_at",
            ),
            limit=limit,
        ),
        "story_reactions": _records(
            StoryReaction.objects.filter(user=user),
            ("id", "story_id", "reaction_type", "created_at", "updated_at"),
            limit=limit,
        ),
        "story_views": _records(
            StoryView.objects.filter(viewer=user),
            ("id", "story_id", "viewed_at"),
            limit=limit,
        ),
        "chat_messages_authored": _records(
            ChatMessage.objects.filter(sender=user),
            (
                "id", "thread_id", "reply_to_id", "text", "is_read",
                "created_at",
            ),
            limit=limit,
        ),
        "chat_attachments_authored": _records(
            ChatAttachment.objects.filter(message__sender=user),
            (
                "id", "message_id", "attachment_type", "content_type",
                "duration_seconds", "original_filename", "file_size",
                "created_at",
            ),
            limit=limit,
        ),
        "calls": _records(
            Call.objects.filter(Q(caller=user) | Q(receiver=user)),
            (
                "id", "thread_id", "caller_id", "receiver_id",
                "call_type", "status", "started_at", "answered_at",
                "ended_at",
            ),
            limit=limit,
        ),
        "call_sessions": _records(
            CallSession.objects.filter(Q(caller=user) | Q(receiver=user)),
            (
                "id", "thread_id", "caller_id", "receiver_id",
                "call_type", "status", "started_at", "accepted_at",
                "ended_at",
            ),
            limit=limit,
        ),
        "ai_messages": _records(
            HeartlyMessage.objects.filter(user=user),
            ("id", "role", "text", "created_at"),
            limit=limit,
        ),
        "notifications": _records(
            Notification.objects.filter(recipient=user),
            (
                "id", "notification_type", "title", "message", "url",
                "is_read", "is_resolved", "created_at", "updated_at",
            ),
            limit=limit,
        ),
        "push_devices": _records(
            PushSubscription.objects.filter(user=user),
            ("id", "user_agent", "enabled", "created_at", "updated_at"),
            limit=limit,
        ),
        "profile_reports_submitted": _records(
            ProfileReport.objects.filter(reporter=user),
            ("id", "reason", "details", "status", "created_at"),
            limit=limit,
        ),
        "post_reports_submitted": _records(
            PostReport.objects.filter(reporter=user),
            ("id", "post_id", "reason", "details", "status", "created_at"),
            limit=limit,
        ),
        "chat_reports_submitted": _records(
            ChatReport.objects.filter(reporter=user),
            (
                "id", "thread_id", "reason", "details", "status",
                "created_at",
            ),
            limit=limit,
        ),
    }

    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        "account": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": user.full_name,
            "phone_number": user.phone_number,
            "gender": user.gender,
            "interested_in": user.interested_in,
            "date_of_birth": _json_value(user.date_of_birth),
            "date_joined": user.date_joined.isoformat(),
            "last_login": _json_value(user.last_login),
            "moderation_status": user.active_moderation_status(),
        },
        "profile": profile_data,
        "interests": interests,
        "collections": collections,
        "export_notes": {
            "per_collection_limit": limit,
            "internal_safety_evidence_excluded": True,
            "moderator_notes_excluded": True,
            "other_members_private_account_data_excluded": True,
            "push_endpoints_and_keys_excluded": True,
        },
    }
