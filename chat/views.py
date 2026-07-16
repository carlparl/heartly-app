import logging
import mimetypes
import re
from pathlib import Path

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.apps import apps
from django.conf import settings
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

try:
    import cloudinary
    import cloudinary.uploader as cloudinary_uploader
except Exception:
    cloudinary = None
    cloudinary_uploader = None

try:
    from profiles.blocking import user_is_hidden_for, hidden_user_ids_for, block_exists_between
except Exception:
    user_is_hidden_for = None
    hidden_user_ids_for = None
    block_exists_between = None

from matches.models import MutualMatch
from profiles.models import Profile, UserBlock

from notifications.activity import (
    notify_chat_message,
    notify_chat_report,
)

from .models import (
    CallSession,
    ChatAttachment,
    ChatMessage,
    ChatReport,
    ChatThread,
)
from .realtime import mark_thread_read_for_user

try:
    from notifications.models import Notification
except Exception:
    Notification = None


User = get_user_model()
logger = logging.getLogger(__name__)

MAX_IMAGE_SIZE = 8 * 1024 * 1024
MAX_VIDEO_SIZE = 75 * 1024 * 1024
MAX_FILE_SIZE = 25 * 1024 * 1024
MAX_AUDIO_SIZE = 15 * 1024 * 1024

# Python's mimetypes module does not reliably map these extensions to an
# audio/* type on every platform (it can return None, or "video/webm" for
# .webm). That wrong/missing Content-Type header is what makes browsers
# refuse to play a saved voice note, even though the file itself is fine.
# Registering them explicitly fixes playback for both the sender and the
# recipient, since it's the same served file and header for both.
mimetypes.add_type("audio/webm", ".webm")
mimetypes.add_type("audio/ogg", ".ogg")
mimetypes.add_type("audio/mp4", ".m4a")
mimetypes.add_type("audio/mp4", ".mp4")
mimetypes.add_type("audio/aac", ".aac")
mimetypes.add_type("audio/wav", ".wav")
mimetypes.add_type("audio/mpeg", ".mp3")

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}

ALLOWED_VIDEO_TYPES = {
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/x-m4v",
    "video/3gpp",
    "video/3gpp2",
}

ALLOWED_AUDIO_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/mpeg",
    "audio/mp4",
    "audio/wav",
    "audio/x-wav",
    "audio/aac",
}

ALLOWED_FILE_TYPES = {
    "application/pdf",
    "text/plain",
    "application/zip",
    "application/x-zip-compressed",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v", ".3gp", ".3g2"}
ALLOWED_AUDIO_EXTENSIONS = {".webm", ".ogg", ".mp3", ".mp4", ".m4a", ".wav", ".aac"}
ALLOWED_FILE_EXTENSIONS = {".pdf", ".txt", ".zip", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}


def model_has_field(model, field_name):
    return any(field.name == field_name for field in model._meta.fields)


def wants_json(request):
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
        or request.POST.get("_ajax") == "1"
    )


def json_success(**extra):
    data = {"ok": True}
    data.update(extra)
    return JsonResponse(data)


def json_error(message, status=400, **extra):
    data = {"ok": False, "message": message}
    data.update(extra)
    return JsonResponse(data, status=status)


def respond_chat_error(request, message, thread=None, status=400):
    if wants_json(request):
        return json_error(message, status=status)

    messages.error(request, message)
    if thread:
        return redirect("chat:chat_room", thread_id=thread.id)
    return redirect("chat:chat_home")


def normalize_client_message_id(raw_value):
    value = (raw_value or "").strip()

    if not value:
        return ""

    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", value):
        return None

    return value


def users_have_mutual_match(user_a, user_b):
    return MutualMatch.objects.filter(
        Q(user_one=user_a, user_two=user_b)
        | Q(user_one=user_b, user_two=user_a)
    ).exists()


def get_profile(user):
    profile, created = Profile.objects.get_or_create(user=user)
    return profile


def get_display_name(user):
    profile = get_profile(user)

    for attr in ("display_name", "name"):
        value = (getattr(profile, attr, "") or "").strip()
        if value:
            return value

    full_name = user.get_full_name()
    if full_name:
        return full_name

    return getattr(user, "username", "") or "Heartly User"


def get_photo_url(user):
    profile = get_profile(user)

    for attr in ("profile_picture", "photo", "avatar", "image"):
        field = getattr(profile, attr, None)
        if field:
            try:
                return field.url
            except Exception:
                pass

    for attr in ("profile_picture", "photo", "avatar", "image"):
        field = getattr(user, attr, None)
        if field:
            try:
                return field.url
            except Exception:
                pass

    return ""


def profile_is_available(user):
    profile = get_profile(user)

    if getattr(profile, "profile_visible", True) is False:
        return False

    if getattr(profile, "hidden_by_moderation", False):
        return False

    return True


def user_hidden_for(viewer, other_user):
    if user_is_hidden_for:
        return user_is_hidden_for(viewer, other_user)
    return False


def hidden_ids_for(user):
    if hidden_user_ids_for:
        return hidden_user_ids_for(user)
    return set()


def blocked_between(user, other_user):
    if not user.is_authenticated or not other_user:
        return True

    if block_exists_between:
        return block_exists_between(user, other_user)

    return UserBlock.objects.filter(blocker=user, blocked=other_user).exists() or UserBlock.objects.filter(
        blocker=other_user,
        blocked=user,
    ).exists()


def validate_upload(uploaded_file, allowed_types, allowed_extensions, max_size, min_size=1):
    if not uploaded_file:
        return "No file was selected."

    if uploaded_file.size < min_size:
        return "File is empty. Please select or record it again."

    content_type = (uploaded_file.content_type or "").lower()
    extension = Path(uploaded_file.name or "").suffix.lower()

    if content_type not in allowed_types and extension not in allowed_extensions:
        return "File type not supported."

    if uploaded_file.size > max_size:
        return "File is too large."

    return None


def safe_file_url(file_field):
    if not file_field:
        return ""

    try:
        return file_field.url
    except Exception:
        return ""


def attachment_label(attachment_type):
    if attachment_type == ChatAttachment.TYPE_IMAGE:
        return "Photo"
    if attachment_type == ChatAttachment.TYPE_VIDEO:
        return "Video"
    if attachment_type == ChatAttachment.TYPE_AUDIO:
        return "Voice note"
    if attachment_type == ChatAttachment.TYPE_FILE:
        return "File"
    return "Message"


def cloudinary_voice_upload_is_available():
    cloudinary_settings = getattr(settings, "CLOUDINARY_STORAGE", {}) or {}

    return (
        cloudinary_uploader is not None
        and cloudinary is not None
        and getattr(settings, "MEDIA_STORAGE_BACKEND", "").strip().lower() == "cloudinary"
        and bool(cloudinary_settings.get("CLOUD_NAME"))
        and bool(cloudinary_settings.get("API_KEY"))
        and bool(cloudinary_settings.get("API_SECRET"))
    )


def ensure_cloudinary_configured():
    if cloudinary is None:
        return

    cloudinary_settings = getattr(settings, "CLOUDINARY_STORAGE", {}) or {}

    cloudinary.config(
        cloud_name=cloudinary_settings.get("CLOUD_NAME", ""),
        api_key=cloudinary_settings.get("API_KEY", ""),
        api_secret=cloudinary_settings.get("API_SECRET", ""),
        secure=True,
    )


def extension_for_audio(uploaded_file):
    extension = Path(uploaded_file.name or "").suffix.lower()

    if extension in ALLOWED_AUDIO_EXTENSIONS:
        return extension

    content_type = (uploaded_file.content_type or "").lower()

    if "ogg" in content_type:
        return ".ogg"

    if "mpeg" in content_type or "mp3" in content_type:
        return ".mp3"

    if "mp4" in content_type or "m4a" in content_type:
        return ".m4a"

    if "wav" in content_type:
        return ".wav"

    if "aac" in content_type:
        return ".aac"

    return ".webm"


def content_type_for_audio(uploaded_file):
    content_type = (uploaded_file.content_type or "").lower().strip()

    if content_type:
        return content_type

    extension = extension_for_audio(uploaded_file)

    if extension == ".ogg":
        return "audio/ogg"

    if extension == ".mp3":
        return "audio/mpeg"

    if extension in [".m4a", ".mp4"]:
        return "audio/mp4"

    if extension == ".wav":
        return "audio/wav"

    if extension == ".aac":
        return "audio/aac"

    return "audio/webm"


def force_url_extension(url, extension):
    if not url or not extension:
        return url

    base, sep, query = url.partition("?")

    if base.lower().endswith(extension.lower()):
        return url

    return base + extension + (sep + query if sep else "")


def upload_voice_note_to_cloudinary(voice_file):
    if not cloudinary_voice_upload_is_available():
        return None

    ensure_cloudinary_configured()

    extension = extension_for_audio(voice_file)
    content_type = content_type_for_audio(voice_file)
    folder = timezone.now().strftime("media/chat_attachments/%Y/%m")

    try:
        if hasattr(voice_file, "seek"):
            voice_file.seek(0)

        upload_result = cloudinary_uploader.upload(
            voice_file,
            resource_type="video",
            folder=folder,
            use_filename=True,
            unique_filename=True,
            overwrite=False,
        )

        secure_url = upload_result.get("secure_url") or upload_result.get("url") or ""
        secure_url = force_url_extension(secure_url, extension)

        if not secure_url:
            raise ValueError("Cloudinary did not return a URL for the voice note.")

        return {
            "url": secure_url,
            "public_id": upload_result.get("public_id", ""),
            "content_type": content_type,
        }

    finally:
        if hasattr(voice_file, "seek"):
            try:
                voice_file.seek(0)
            except Exception:
                pass


def guessed_mime_type(attachment):
    stored_content_type = (getattr(attachment, "content_type", "") or "").strip()

    if stored_content_type:
        return stored_content_type

    name = attachment.original_filename or (attachment.file.name if attachment.file else "")
    guessed, _ = mimetypes.guess_type(name or "")
    return guessed or ""


def playable_file_url(attachment):
    url = (getattr(attachment, "external_url", "") or "").strip()

    if not url:
        url = safe_file_url(attachment.file)

    if not url:
        return ""

    name = attachment.original_filename or (attachment.file.name if attachment.file else "")
    extension = Path(name).suffix.lower()

    if attachment.attachment_type == ChatAttachment.TYPE_AUDIO and extension:
        return force_url_extension(url, extension)

    return url


def serialize_attachment(attachment):
    return {
        "id": attachment.id,
        "type": attachment.attachment_type,
        "url": playable_file_url(attachment),
        "name": attachment.original_filename or attachment_label(attachment.attachment_type),
        "size": attachment.file_size,
        "content_type": guessed_mime_type(attachment),
        "duration_seconds": getattr(attachment, "duration_seconds", 0) or 0,
    }


def reply_preview(message):
    if not message:
        return None

    first_attachment = message.attachments.first()

    if message.text:
        text = message.text[:110]
    elif first_attachment:
        text = attachment_label(first_attachment.attachment_type)
    else:
        text = "Message"

    return {
        "id": message.id,
        "sender_id": message.sender_id,
        "sender_name": get_display_name(message.sender),
        "text": text,
    }


def serialize_message(message):
    return {
        "id": message.id,
        "message_id": message.id,
        "thread_id": message.thread_id,
        "sender_id": message.sender_id,
        "sender_name": get_display_name(message.sender),
        "text": message.text,
        "client_message_id": message.client_message_id,
        "created_at": timezone.localtime(message.created_at).strftime("%H:%M"),
        "is_read": message.is_read,
        "reply_to": reply_preview(message.reply_to),
        "attachments": [serialize_attachment(attachment) for attachment in message.attachments.all()],
    }


def create_message_notification(message):
    if Notification is None:
        return

    thread = message.thread
    sender = message.sender
    recipient = thread.other_user(sender)

    if blocked_between(sender, recipient):
        return

    try:
        notification_data = {
            "recipient": recipient,
            "actor": sender,
        }

        if model_has_field(Notification, "notification_type"):
            notification_data["notification_type"] = getattr(Notification, "TYPE_MESSAGE", "message")

        if model_has_field(Notification, "title"):
            notification_data["title"] = "New message"

        if model_has_field(Notification, "message"):
            notification_data["message"] = f"{get_display_name(sender)} sent you a message."

        if model_has_field(Notification, "url"):
            notification_data["url"] = reverse("chat:chat_room", args=[thread.id])

        if model_has_field(Notification, "related_object_type"):
            notification_data["related_object_type"] = "chat.chatmessage"

        if model_has_field(Notification, "related_object_id"):
            notification_data["related_object_id"] = message.id

        Notification.objects.create(**notification_data)
    except Exception:
        logger.exception(
            "Could not create chat message notification.",
            extra={
                "message_id": message.id,
                "thread_id": message.thread_id,
            },
        )


def broadcast_message(message):
    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    try:
        async_to_sync(channel_layer.group_send)(
            f"chat_thread_{message.thread_id}",
            {
                "type": "chat.broadcast",
                "payload": {
                    "type": "chat.message",
                    **serialize_message(message),
                },
            },
        )
    except Exception:
        logger.exception(
            "Could not broadcast committed chat message.",
            extra={
                "message_id": message.id,
                "thread_id": message.thread_id,
            },
        )


def latest_message_preview(message, viewer):
    if not message:
        return "Start the conversation."

    prefix = "You: " if message.sender_id == viewer.id else ""

    if message.text:
        return f"{prefix}{message.text}"

    attachment = message.attachments.first()
    if attachment:
        return f"{prefix}{attachment_label(attachment.attachment_type)}"

    return "New message"


def build_thread_card(thread, user):
    other_user = thread.other_user(user)

    latest_message = (
        thread.messages
        .select_related("sender", "reply_to", "reply_to__sender")
        .prefetch_related("attachments", "reply_to__attachments")
        .order_by("-created_at")
        .first()
    )

    unread_count = thread.messages.filter(is_read=False).exclude(sender=user).count()

    return {
        "thread": thread,
        "other_user": other_user,
        "name": get_display_name(other_user),
        "photo": get_photo_url(other_user),
        "latest_message": latest_message,
        "latest_preview": latest_message_preview(latest_message, user),
        "unread_count": unread_count,
    }


@login_required
def chat_home(request):
    hidden_ids = hidden_ids_for(request.user)

    threads = (
        ChatThread.objects
        .filter(Q(user_one=request.user) | Q(user_two=request.user))
        .exclude(user_one_id__in=hidden_ids)
        .exclude(user_two_id__in=hidden_ids)
        .select_related("user_one", "user_two")
        .prefetch_related("messages", "messages__attachments")
        .order_by("-updated_at")
    )

    thread_cards = []

    for thread in threads:
        other_user = thread.other_user(request.user)

        if blocked_between(request.user, other_user):
            continue

        if not profile_is_available(other_user):
            continue

        thread_cards.append(build_thread_card(thread, request.user))

    return render(request, "chat/chat_home.html", {"thread_cards": thread_cards})


@login_required
def start_chat(request, user_id):
    other_user = get_object_or_404(
        User,
        id=user_id,
        is_active=True,
    )

    if other_user == request.user:
        messages.error(
            request,
            "You cannot start a chat with yourself.",
        )
        return redirect("chat:chat_home")

    if user_hidden_for(request.user, other_user):
        messages.error(
            request,
            "This user is not available for chat.",
        )
        return redirect("matches:discover")

    if not users_have_mutual_match(
        request.user,
        other_user,
    ):
        messages.error(
            request,
            "You can start chatting after you both match.",
        )
        return redirect("matches:discover")

    thread = ChatThread.get_or_create_between(
        request.user,
        other_user,
    )
    return redirect(
        "chat:chat_room",
        thread_id=thread.id,
    )

@login_required
def chat_room(request, thread_id):
    thread = get_object_or_404(
        ChatThread.objects.select_related("user_one", "user_two"),
        id=thread_id,
    )

    if not thread.has_user(request.user):
        messages.error(request, "This chat is not available.")
        return redirect("chat:chat_home")

    other_user = thread.other_user(request.user)

    if blocked_between(request.user, other_user):
        messages.error(request, "This chat is not available.")
        return redirect("chat:chat_home")

    if user_hidden_for(request.user, other_user):
        messages.error(request, "This chat is no longer available.")
        return redirect("chat:chat_home")

    mark_thread_read_for_user(
        thread.id,
        request.user,
    )

    chat_messages = list(
        thread.messages
        .select_related("sender", "reply_to", "reply_to__sender")
        .prefetch_related("attachments", "reply_to__attachments")
        .order_by("created_at")
    )
    for message in chat_messages:
        for attachment in message.attachments.all():
            attachment.playable_url = playable_file_url(attachment)
        if message.reply_to:
            for attachment in message.reply_to.attachments.all():
                attachment.playable_url = playable_file_url(attachment)

    return render(
        request,
        "chat/chat_room.html",
        {
            "thread": thread,
            "chat_messages": chat_messages,
            "other_user": other_user,
            "other_profile": get_profile(other_user),
            "other_user_name": get_display_name(other_user),
            "other_user_photo": get_photo_url(other_user),
            "current_user_name": get_display_name(request.user),
            "current_user_photo": get_photo_url(request.user),
        },
    )


@login_required
@require_POST
def send_message(request, thread_id):
    thread = get_object_or_404(
        ChatThread.objects.select_related(
            "user_one",
            "user_two",
        ),
        id=thread_id,
    )

    if not thread.has_user(request.user):
        return respond_chat_error(
            request,
            "This chat is not available.",
            status=403,
        )

    other_user = thread.other_user(request.user)

    if blocked_between(request.user, other_user):
        return respond_chat_error(
            request,
            "You cannot message this user.",
            thread=thread,
            status=403,
        )

    if not other_user.is_active or not profile_is_available(other_user):
        return respond_chat_error(
            request,
            "This chat is no longer available.",
            thread=thread,
            status=403,
        )

    client_message_id = normalize_client_message_id(
        request.POST.get("client_message_id", "")
    )

    if client_message_id is None:
        return respond_chat_error(
            request,
            "Invalid message request identifier.",
            thread=thread,
            status=400,
        )

    if client_message_id:
        existing_message = (
            ChatMessage.objects
            .filter(
                thread=thread,
                sender=request.user,
                client_message_id=client_message_id,
            )
            .select_related(
                "sender",
                "reply_to",
                "reply_to__sender",
            )
            .prefetch_related(
                "attachments",
                "reply_to__attachments",
            )
            .first()
        )

        if existing_message is not None:
            if wants_json(request):
                return json_success(
                    message=serialize_message(existing_message),
                    duplicate=True,
                )

            return redirect(
                "chat:chat_room",
                thread_id=thread.id,
            )

    text = (request.POST.get("text") or "").strip()

    if len(text) > 1200:
        return respond_chat_error(
            request,
            "Message is too long. Maximum length is 1200 characters.",
            thread=thread,
            status=400,
        )

    image_file = request.FILES.get("image")
    video_file = request.FILES.get("video")
    regular_file = request.FILES.get("file")
    voice_file = (
        request.FILES.get("voice")
        or request.FILES.get("audio")
    )

    if (
        not text
        and not image_file
        and not video_file
        and not regular_file
        and not voice_file
    ):
        return respond_chat_error(
            request,
            "Message cannot be empty.",
            thread=thread,
        )

    upload_checks = [
        (
            image_file,
            ALLOWED_IMAGE_TYPES,
            ALLOWED_IMAGE_EXTENSIONS,
            MAX_IMAGE_SIZE,
            1,
        ),
        (
            video_file,
            ALLOWED_VIDEO_TYPES,
            ALLOWED_VIDEO_EXTENSIONS,
            MAX_VIDEO_SIZE,
            1,
        ),
        (
            regular_file,
            ALLOWED_FILE_TYPES,
            ALLOWED_FILE_EXTENSIONS,
            MAX_FILE_SIZE,
            1,
        ),
        (
            voice_file,
            ALLOWED_AUDIO_TYPES,
            ALLOWED_AUDIO_EXTENSIONS,
            MAX_AUDIO_SIZE,
            300,
        ),
    ]

    for (
        uploaded_file,
        allowed_types,
        allowed_extensions,
        max_size,
        min_size,
    ) in upload_checks:
        if not uploaded_file:
            continue

        error = validate_upload(
            uploaded_file,
            allowed_types,
            allowed_extensions,
            max_size,
            min_size=min_size,
        )

        if error:
            return respond_chat_error(
                request,
                error,
                thread=thread,
            )

    reply_to = None
    reply_to_id = (
        request.POST.get("reply_to_id") or ""
    ).strip()

    if reply_to_id:
        reply_to = ChatMessage.objects.filter(
            id=reply_to_id,
            thread=thread,
        ).first()

        if reply_to is None:
            return respond_chat_error(
                request,
                "The message you are replying to is not available.",
                thread=thread,
            )

    voice_upload = None

    if voice_file and cloudinary_voice_upload_is_available():
        try:
            voice_upload = upload_voice_note_to_cloudinary(voice_file)
        except Exception:
            logger.exception(
                "Voice note upload failed.",
                extra={
                    "thread_id": thread.id,
                    "sender_id": request.user.id,
                },
            )
            return respond_chat_error(
                request,
                "Voice note upload failed. Please try again.",
                thread=thread,
                status=500,
            )

    message = None
    created_message = False

    try:
        with transaction.atomic():
            message = ChatMessage.objects.create(
                thread=thread,
                sender=request.user,
                reply_to=reply_to,
                text=text,
                client_message_id=client_message_id or "",
            )
            created_message = True

            if image_file:
                ChatAttachment.objects.create(
                    message=message,
                    attachment_type=ChatAttachment.TYPE_IMAGE,
                    file=image_file,
                    original_filename=image_file.name,
                    file_size=image_file.size,
                    content_type=image_file.content_type or "",
                )

            if video_file:
                ChatAttachment.objects.create(
                    message=message,
                    attachment_type=ChatAttachment.TYPE_VIDEO,
                    file=video_file,
                    original_filename=video_file.name,
                    file_size=video_file.size,
                    content_type=video_file.content_type or "",
                )

            if regular_file:
                ChatAttachment.objects.create(
                    message=message,
                    attachment_type=ChatAttachment.TYPE_FILE,
                    file=regular_file,
                    original_filename=regular_file.name,
                    file_size=regular_file.size,
                    content_type=regular_file.content_type or "",
                )

            if voice_file:
                voice_name = (
                    voice_file.name
                    or "heartly-voice-note.webm"
                )

                if voice_upload:
                    ChatAttachment.objects.create(
                        message=message,
                        attachment_type=ChatAttachment.TYPE_AUDIO,
                        file=None,
                        external_url=voice_upload["url"],
                        cloudinary_public_id=voice_upload.get(
                            "public_id",
                            "",
                        ),
                        original_filename=voice_name,
                        file_size=voice_file.size,
                        content_type=(
                            voice_upload.get("content_type", "")
                            or content_type_for_audio(voice_file)
                        ),
                    )
                else:
                    ChatAttachment.objects.create(
                        message=message,
                        attachment_type=ChatAttachment.TYPE_AUDIO,
                        file=voice_file,
                        original_filename=voice_name,
                        file_size=voice_file.size,
                        content_type=content_type_for_audio(voice_file),
                    )

            thread.save(update_fields=["updated_at"])

    except IntegrityError:
        if not client_message_id:
            logger.exception(
                "Chat message database write failed.",
                extra={
                    "thread_id": thread.id,
                    "sender_id": request.user.id,
                },
            )
            return respond_chat_error(
                request,
                "Message could not be saved.",
                thread=thread,
                status=500,
            )

        message = (
            ChatMessage.objects
            .filter(
                thread=thread,
                sender=request.user,
                client_message_id=client_message_id,
            )
            .first()
        )

        if message is None:
            logger.exception(
                "Idempotent chat message recovery failed.",
                extra={
                    "thread_id": thread.id,
                    "sender_id": request.user.id,
                    "client_message_id": client_message_id,
                },
            )
            return respond_chat_error(
                request,
                "Message could not be saved.",
                thread=thread,
                status=500,
            )

        created_message = False

    except Exception:
        logger.exception(
            "Chat message or attachment save failed.",
            extra={
                "thread_id": thread.id,
                "sender_id": request.user.id,
            },
        )
        return respond_chat_error(
            request,
            "Upload failed. Please try again.",
            thread=thread,
            status=500,
        )

    message = (
        ChatMessage.objects
        .select_related(
            "sender",
            "reply_to",
            "reply_to__sender",
        )
        .prefetch_related(
            "attachments",
            "reply_to__attachments",
        )
        .get(id=message.id)
    )

    if created_message:
        notify_chat_message(message)
        broadcast_message(message)

    if wants_json(request):
        return json_success(
            message=serialize_message(message),
            duplicate=not created_message,
        )

    return redirect(
        "chat:chat_room",
        thread_id=thread.id,
    )

@login_required
@require_POST
def delete_selected_messages(request, thread_id):
    thread = get_object_or_404(ChatThread, id=thread_id)

    if not thread.has_user(request.user):
        messages.error(request, "This chat is not available.")
        return redirect("chat:chat_home")

    selected_ids = request.POST.getlist("message_ids")

    if not selected_ids:
        messages.error(request, "Select at least one message.")
        return redirect("chat:chat_room", thread_id=thread.id)

    deleted_count, deleted_objects = ChatMessage.objects.filter(
        thread=thread,
        sender=request.user,
        id__in=selected_ids,
    ).delete()

    if deleted_count:
        messages.success(request, "Selected messages removed.")
    else:
        messages.error(request, "You can only delete messages you sent.")

    return redirect("chat:chat_room", thread_id=thread.id)


@login_required
@require_POST
def block_thread_user(request, thread_id):
    thread = get_object_or_404(ChatThread, id=thread_id)

    if not thread.has_user(request.user):
        messages.error(request, "This chat is not available.")
        return redirect("chat:chat_home")

    other_user = thread.other_user(request.user)
    UserBlock.objects.get_or_create(blocker=request.user, blocked=other_user)

    messages.success(request, "User blocked.")
    return redirect("chat:chat_home")


def create_chat_report_staff_alert(report):
    if Notification is None:
        return

    staff_users = User.objects.filter(is_staff=True, is_active=True).exclude(id=report.reporter_id)
    channel_layer = get_channel_layer()
    reporter_name = get_display_name(report.reporter)

    for staff_user in staff_users:
        url = reverse("chat:chat_room", args=[report.thread.id])
        data = {
            "recipient": staff_user,
            "actor": report.reporter,
            "notification_type": getattr(Notification, "TYPE_REPORT", "report"),
            "title": "Chat report",
            "message": f"{reporter_name} reported a chat.",
            "url": url,
            "related_object_type": "chat.chatreport",
            "related_object_id": report.id,
        }
        allowed_data = {key: value for key, value in data.items() if model_has_field(Notification, key)}

        try:
            Notification.objects.create(**allowed_data)
        except Exception:
            continue

        if channel_layer:
            try:
                async_to_sync(channel_layer.group_send)(
                    f"heartly_user_{staff_user.id}",
                    {
                        "type": "notification.event",
                        "payload": {
                            "type": "feed_notification",
                            "notification_type": "report",
                            "title": "Chat report",
                            "message": f"{reporter_name} reported a chat.",
                            "url": url,
                        },
                    },
                )
            except Exception:
                pass


def build_call_payload(call):
    call_url = reverse("chat:call_room", args=[call.id])

    return {
        "call_id": call.id,
        "thread_id": call.thread_id,
        "call_type": call.call_type,
        "caller_id": call.caller_id,
        "receiver_id": call.receiver_id,
        "caller_name": get_display_name(call.caller),
        "receiver_name": get_display_name(call.receiver),
        "url": call_url,
        "accept_url": call_url,
        "decline_url": reverse("chat:decline_call", args=[call.id]),
        "end_url": reverse("chat:end_call", args=[call.id]),
    }


def broadcast_call_event(call, event_type):
    channel_layer = get_channel_layer()

    if not channel_layer:
        return

    payload = build_call_payload(call)

    # Open chat room receives the same call events.
    try:
        async_to_sync(channel_layer.group_send)(
            f"chat_thread_{call.thread_id}",
            {
                "type": "chat.broadcast",
                "payload": {
                    "type": event_type,
                    **payload,
                },
            },
        )
    except Exception:
        pass

    # Global listener receives calls even when the user is on Feed, Matches,
    # Profile, AI, Settings, etc.
    notification_type = {
        "call.incoming": "incoming_call",
        "call.accepted": "call_accepted",
        "call.declined": "call_declined",
        "call.ended": "call_ended",
        "call.missed": "missed_call",
    }.get(event_type, event_type.replace(".", "_"))

    if event_type == "call.incoming":
        target_ids = [call.receiver_id]
    else:
        target_ids = list({call.caller_id, call.receiver_id})

    for user_id in target_ids:
        try:
            async_to_sync(channel_layer.group_send)(
                f"heartly_user_{user_id}",
                {
                    "type": "notification.event",
                    "payload": {
                        "type": notification_type,
                        **payload,
                    },
                },
            )
        except Exception:
            pass


def resolve_call_notification(call, recipient):
    if Notification is None:
        return

    Notification.objects.filter(
        recipient=recipient,
        notification_type=Notification.TYPE_CALL,
        related_object_type="chat.callsession",
        related_object_id=call.id,
    ).update(is_read=True, is_resolved=True)


@login_required
def start_call(request, thread_id, call_type):
    thread = get_object_or_404(
        ChatThread.objects.select_related("user_one", "user_two"),
        id=thread_id,
    )

    if not thread.has_user(request.user):
        messages.error(request, "You do not have access to this chat.")
        return redirect("chat:chat_home")

    other_user = thread.other_user(request.user)

    if blocked_between(request.user, other_user):
        messages.error(request, "This call is not available.")
        return redirect("chat:chat_home")

    if call_type not in [CallSession.CALL_AUDIO, CallSession.CALL_VIDEO]:
        messages.error(request, "Invalid call type.")
        return redirect("chat:chat_room", thread_id=thread.id)

    call = CallSession.objects.create(
        thread=thread,
        caller=request.user,
        receiver=other_user,
        call_type=call_type,
        status=CallSession.STATUS_RINGING,
    )

    broadcast_call_event(call, "call.incoming")

    if Notification is not None:
        Notification.objects.create(
            recipient=other_user,
            actor=request.user,
            notification_type=Notification.TYPE_CALL,
            title=(
                "Incoming video call"
                if call_type == CallSession.CALL_VIDEO
                else "Incoming audio call"
            ),
            message=f"{get_display_name(request.user)} is calling you.",
            url=reverse("chat:call_room", args=[call.id]),
            related_object_type="chat.callsession",
            related_object_id=call.id,
        )

    if wants_json(request):
        return json_success(
            message="Call started.",
            call=build_call_payload(call),
            call_url=reverse("chat:call_room", args=[call.id]),
        )

    return redirect("chat:call_room", call_id=call.id)


@login_required
def call_room(request, call_id):
    call = get_object_or_404(
        CallSession.objects.select_related("thread", "caller", "receiver"),
        id=call_id,
    )

    thread = call.thread

    if not thread.has_user(request.user):
        messages.error(request, "You do not have access to this call.")
        return redirect("chat:chat_home")

    # Receiver accepts by opening the call room from the global incoming-call
    # banner. This notifies the caller wherever they currently are.
    if request.user == call.receiver and call.status == CallSession.STATUS_RINGING:
        call.status = CallSession.STATUS_ACCEPTED
        call.accepted_at = timezone.now()
        call.save(update_fields=["status", "accepted_at"])
        broadcast_call_event(call, "call.accepted")
        resolve_call_notification(call, request.user)

    other_user = call.receiver if request.user == call.caller else call.caller

    return render(
        request,
        "chat/call_room.html",
        {
            "call": call,
            "thread": thread,
            "call_type": call.call_type,
            "other_user": other_user,
            "other_user_name": get_display_name(other_user),
            "other_user_photo": get_photo_url(other_user),
            "ice_servers": settings.HEARTLY_ICE_SERVERS,
        },
    )


@login_required
@require_POST
def accept_call(request, call_id):
    call = get_object_or_404(
        CallSession.objects.select_related("thread", "caller", "receiver"),
        id=call_id,
    )

    if request.user != call.receiver:
        if wants_json(request):
            return json_error("Only the receiver can accept this call.", status=403)

        messages.error(request, "Only the receiver can accept this call.")
        return redirect("chat:chat_room", thread_id=call.thread.id)

    if call.status == CallSession.STATUS_RINGING:
        call.status = CallSession.STATUS_ACCEPTED
        call.accepted_at = timezone.now()
        call.save(update_fields=["status", "accepted_at"])
        broadcast_call_event(call, "call.accepted")
        resolve_call_notification(call, request.user)

    if wants_json(request):
        return json_success(call=build_call_payload(call))

    return redirect("chat:call_room", call_id=call.id)


@login_required
@require_POST
def decline_call(request, call_id):
    call = get_object_or_404(
        CallSession.objects.select_related("thread", "caller", "receiver"),
        id=call_id,
    )

    if request.user not in [call.caller, call.receiver]:
        if wants_json(request):
            return json_error("You do not have access to this call.", status=403)

        messages.error(request, "You do not have access to this call.")
        return redirect("chat:chat_home")

    call.status = CallSession.STATUS_DECLINED
    call.ended_at = timezone.now()
    call.save(update_fields=["status", "ended_at"])
    broadcast_call_event(call, "call.declined")
    resolve_call_notification(call, call.receiver)

    if wants_json(request):
        return json_success(call=build_call_payload(call))

    return redirect("chat:chat_room", thread_id=call.thread.id)


@login_required
@require_POST
def end_call(request, call_id):
    call = get_object_or_404(
        CallSession.objects.select_related("thread", "caller", "receiver"),
        id=call_id,
    )

    if request.user not in [call.caller, call.receiver]:
        if wants_json(request):
            return json_error("You do not have access to this call.", status=403)

        messages.error(request, "You do not have access to this call.")
        return redirect("chat:chat_home")

    call.status = CallSession.STATUS_ENDED
    call.ended_at = timezone.now()
    call.save(update_fields=["status", "ended_at"])
    broadcast_call_event(call, "call.ended")
    resolve_call_notification(call, call.receiver)

    if wants_json(request):
        return json_success(call=build_call_payload(call))

    return redirect("chat:chat_room", thread_id=call.thread.id)


@login_required
@require_POST
def report_thread_user(request, thread_id):
    thread = get_object_or_404(ChatThread.objects.select_related("user_one", "user_two"), id=thread_id)

    if not thread.has_user(request.user):
        messages.error(request, "You cannot report this chat.")
        return redirect("chat:chat_home")

    reported_user = thread.other_user(request.user)
    reason = (request.POST.get("reason") or ChatReport.REASON_OTHER).strip()
    details = (request.POST.get("details") or "").strip()
    valid_reasons = [choice[0] for choice in ChatReport.REASON_CHOICES]

    if reason not in valid_reasons:
        reason = ChatReport.REASON_OTHER

    report = ChatReport.objects.create(
        thread=thread,
        reporter=request.user,
        reported_user=reported_user,
        reason=reason,
        details=details,
    )

    notify_chat_report(report)

    if wants_json(request):
        return json_success(message="Chat reported.")

    messages.success(request, "Chat reported.")
    return redirect("chat:chat_room", thread.id)


def optional_chat_model(model_name):
    try:
        return apps.get_model("chat", model_name)
    except LookupError:
        return None


def set_available_boolean_fields(instance, field_names):
    changed = []

    for field_name in field_names:
        if model_has_field(instance.__class__, field_name):
            setattr(instance, field_name, True)
            changed.append(field_name)

    for field_name in ["hidden_at", "deleted_at", "cleared_at"]:
        if model_has_field(instance.__class__, field_name):
            setattr(instance, field_name, timezone.now())
            changed.append(field_name)

    if changed:
        instance.save(update_fields=list(dict.fromkeys(changed)))

    return bool(changed)


def hide_messages_for_user(thread, user, message_ids=None):
    MessageState = optional_chat_model("ChatMessageUserState")
    qs = ChatMessage.objects.filter(thread=thread)

    if message_ids is not None:
        qs = qs.filter(id__in=message_ids)

    if MessageState is None:
        # Never delete shared messages as a fallback for
        # a per-user hide operation.
        return 0

    count = 0
    for message in qs:
        state, created = MessageState.objects.get_or_create(message=message, user=user)
        changed = set_available_boolean_fields(
            state,
            ["hidden_for_me", "deleted_for_me", "is_hidden", "is_deleted", "is_cleared"],
        )
        if not changed:
            state.save()
        count += 1

    return count


@login_required
@require_POST
def clear_chat_for_me(request, thread_id):
    thread = get_object_or_404(
        ChatThread,
        id=thread_id,
    )

    if not thread.has_user(request.user):
        return respond_chat_error(
            request,
            "This chat is not available.",
            status=403,
        )

    return respond_chat_error(
        request,
        (
            "Clear for me is temporarily disabled "
            "while private message-state storage is rebuilt."
        ),
        thread=thread,
        status=409,
    )

@login_required
@require_POST
def delete_chat_for_me(request, thread_id):
    thread = get_object_or_404(
        ChatThread,
        id=thread_id,
    )

    if not thread.has_user(request.user):
        return respond_chat_error(
            request,
            "This chat is not available.",
            status=403,
        )

    return respond_chat_error(
        request,
        (
            "Delete for me is temporarily disabled "
            "while private message-state storage is rebuilt."
        ),
        thread=thread,
        status=409,
    )

@login_required
def open_message_attachment(request, message_id):
    message = get_object_or_404(
        ChatMessage.objects.select_related("thread", "sender").prefetch_related("attachments"),
        id=message_id,
    )

    thread = message.thread

    if not thread.has_user(request.user):
        messages.error(request, "This attachment is not available.")
        return redirect("chat:chat_home")

    attachment = message.attachments.first()

    if not attachment or not getattr(attachment, "file", None):
        messages.error(request, "Attachment not found.")
        return redirect("chat:chat_room", thread_id=thread.id)

    if request.user != message.sender:
        changed = []

        for field_name in ["opened_at", "viewed_at", "seen_at"]:
            if model_has_field(attachment.__class__, field_name):
                setattr(attachment, field_name, timezone.now())
                changed.append(field_name)

        for field_name in ["is_opened", "is_viewed", "has_been_opened"]:
            if model_has_field(attachment.__class__, field_name):
                setattr(attachment, field_name, True)
                changed.append(field_name)

        if changed:
            attachment.save(update_fields=list(dict.fromkeys(changed)))

    return redirect(attachment.file.url)


@login_required
@require_POST
def delete_selected_messages_for_me(request):
    if wants_json(request):
        return json_error(
            "Delete for me is temporarily disabled.",
            status=409,
        )

    messages.info(
        request,
        "Delete for me is temporarily disabled.",
    )
    next_url = (
        request.POST.get("next")
        or request.META.get("HTTP_REFERER")
        or reverse("chat:chat_home")
    )
    return redirect(next_url)

@login_required
@require_POST
def delete_selected_messages_for_everyone(request):
    selected_ids = request.POST.getlist("message_ids")
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or reverse("chat:chat_home")

    if not selected_ids:
        messages.error(request, "Select at least one message.")
        return redirect(next_url)

    qs = ChatMessage.objects.filter(id__in=selected_ids, sender=request.user).filter(
        Q(thread__user_one=request.user) | Q(thread__user_two=request.user)
    )

    soft_fields = ["deleted_for_everyone", "is_deleted_for_everyone", "is_deleted"]
    can_soft_delete = any(model_has_field(ChatMessage, field_name) for field_name in soft_fields)

    if can_soft_delete:
        update_data = {}

        for field_name in soft_fields:
            if model_has_field(ChatMessage, field_name):
                update_data[field_name] = True

        if model_has_field(ChatMessage, "text"):
            update_data["text"] = ""

        if model_has_field(ChatMessage, "deleted_at"):
            update_data["deleted_at"] = timezone.now()

        deleted_count = qs.update(**update_data)
    else:
        deleted_count, deleted_objects = qs.delete()

    if deleted_count:
        messages.success(request, "Selected messages deleted for everyone.")
    else:
        messages.error(request, "You can only delete messages you sent.")

    return redirect(next_url)


@login_required
@require_POST
def delete_chat(request, thread_id):
    thread = get_object_or_404(
        ChatThread,
        id=thread_id,
    )

    if not thread.has_user(request.user):
        return respond_chat_error(
            request,
            "This chat is not available.",
            status=403,
        )

    return respond_chat_error(
        request,
        (
            "Permanent shared chat deletion is "
            "disabled during the rebuild."
        ),
        thread=thread,
        status=409,
    )
