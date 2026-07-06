from pathlib import Path

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.urls import reverse

from profiles.models import Profile, UserBlock
from profiles.blocking import user_is_hidden_for

from .models import ChatAttachment, ChatMessage, ChatReport, ChatThread


try:
    from profiles.blocking import hidden_user_ids_for, block_exists_between
except Exception:
    hidden_user_ids_for = None
    block_exists_between = None

try:
    from notifications.models import Notification
except Exception:
    Notification = None


User = get_user_model()

try:
    from notifications.models import Notification
except Exception:
    Notification = None


User = get_user_model()


MAX_IMAGE_SIZE = 8 * 1024 * 1024
MAX_VIDEO_SIZE = 50 * 1024 * 1024
MAX_FILE_SIZE = 25 * 1024 * 1024

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

ALLOWED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
}

ALLOWED_VIDEO_EXTENSIONS = {
    ".mp4",
    ".webm",
    ".mov",
}

ALLOWED_FILE_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".zip",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
}


def get_profile(user):
    profile, created = Profile.objects.get_or_create(user=user)
    return profile


def get_display_name(user):
    profile = get_profile(user)

    if getattr(profile, "display_name", None):
        return profile.display_name

    full_name = user.get_full_name()

    if full_name:
        return full_name

    return user.username


def get_photo_url(user):
    profile = get_profile(user)

    if getattr(profile, "profile_picture", None):
        try:
            return profile.profile_picture.url
        except Exception:
            return ""

    return ""


def profile_is_available(user):
    profile = get_profile(user)

    if getattr(profile, "profile_visible", True) is False:
        return False

    if getattr(profile, "hidden_by_moderation", False):
        return False

    return True


def hidden_ids_for(user):
    if hidden_user_ids_for:
        return hidden_user_ids_for(user)

    return set()


def blocked_between(user, other_user):
    if not user.is_authenticated or not other_user:
        return True

    if block_exists_between:
        return block_exists_between(user, other_user)

    return UserBlock.objects.filter(
        blocker=user,
        blocked=other_user,
    ).exists() or UserBlock.objects.filter(
        blocker=other_user,
        blocked=user,
    ).exists()


def validate_upload(uploaded_file, allowed_types, allowed_extensions, max_size):
    content_type = (uploaded_file.content_type or "").lower()
    extension = Path(uploaded_file.name or "").suffix.lower()

    if content_type not in allowed_types and extension not in allowed_extensions:
        return "File type not supported."

    if uploaded_file.size > max_size:
        return "File is too large."

    return None


def model_has_field(model, field_name):
    return any(field.name == field_name for field in model._meta.fields)


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
        return


def latest_message_preview(message, viewer):
    if not message:
        return "Start the conversation."

    prefix = "You: " if message.sender_id == viewer.id else ""

    if message.text:
        return f"{prefix}{message.text}"

    attachment = message.attachments.first()

    if not attachment:
        return "New message"

    if attachment.attachment_type == ChatAttachment.TYPE_IMAGE:
        return f"{prefix}Photo"

    if attachment.attachment_type == ChatAttachment.TYPE_VIDEO:
        return f"{prefix}Video"

    if attachment.attachment_type == ChatAttachment.TYPE_FILE:
        return f"{prefix}File"

    return "New message"


def build_thread_card(thread, user):
    other_user = thread.other_user(user)

    latest_message = (
        thread.messages
        .prefetch_related("attachments")
        .order_by("-created_at")
        .first()
    )

    unread_count = (
        thread.messages
        .filter(is_read=False)
        .exclude(sender=user)
        .count()
    )

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

    return render(
        request,
        "chat/chat_home.html",
        {
            "thread_cards": thread_cards,
        },
    )


@login_required
def start_chat(request, user_id):
    other_user = get_object_or_404(User, id=user_id)

    if other_user == request.user:
        messages.error(request, "You cannot start a chat with yourself.")
        return redirect("chat:chat_home")

    if user_is_hidden_for(request.user, other_user):
        messages.error(request, "This user is not available for chat.")
        return redirect("matches:discover")

    thread = ChatThread.get_or_create_between(request.user, other_user)

    return redirect("chat:chat_room", thread.id)


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

    other_profile = get_profile(other_user)

    if user_is_hidden_for(request.user, other_user):
        messages.error(request, "This chat is no longer available.")
        return redirect("chat:chat_home")

    ChatMessage.objects.filter(
        thread=thread,
        is_read=False,
    ).exclude(
        sender=request.user,
    ).update(is_read=True)

    chat_messages = (
        thread.messages
        .select_related("sender")
        .prefetch_related("attachments")
        .order_by("created_at")
    )

    return render(
        request,
        "chat/chat_room.html",
        {
            "thread": thread,
            "chat_messages": chat_messages,
            "other_user": other_user,
            "other_profile": other_profile,
            "other_user_name": get_display_name(other_user),
            "other_user_photo": get_photo_url(other_user),
        },
    )


@login_required
@require_POST
def send_message(request, thread_id):
    thread = get_object_or_404(ChatThread, id=thread_id)

    if not thread.has_user(request.user):
        messages.error(request, "This chat is not available.")
        return redirect("chat:chat_home")

    other_user = thread.other_user(request.user)

    if blocked_between(request.user, other_user):
        messages.error(request, "You cannot message this user.")
        return redirect("chat:chat_home")

    text = request.POST.get("text", "").strip()
    image_file = request.FILES.get("image")
    video_file = request.FILES.get("video")
    regular_file = request.FILES.get("file")

    if not text and not image_file and not video_file and not regular_file:
        messages.error(request, "Message cannot be empty.")
        return redirect("chat:chat_room", thread_id=thread.id)

    if image_file:
        error = validate_upload(
            image_file,
            ALLOWED_IMAGE_TYPES,
            ALLOWED_IMAGE_EXTENSIONS,
            MAX_IMAGE_SIZE,
        )

        if error:
            messages.error(request, error)
            return redirect("chat:chat_room", thread_id=thread.id)

    if video_file:
        error = validate_upload(
            video_file,
            ALLOWED_VIDEO_TYPES,
            ALLOWED_VIDEO_EXTENSIONS,
            MAX_VIDEO_SIZE,
        )

        if error:
            messages.error(request, error)
            return redirect("chat:chat_room", thread_id=thread.id)

    if regular_file:
        error = validate_upload(
            regular_file,
            ALLOWED_FILE_TYPES,
            ALLOWED_FILE_EXTENSIONS,
            MAX_FILE_SIZE,
        )

        if error:
            messages.error(request, error)
            return redirect("chat:chat_room", thread_id=thread.id)

    message = ChatMessage.objects.create(
        thread=thread,
        sender=request.user,
        text=text,
    )

    if image_file:
        ChatAttachment.objects.create(
            message=message,
            attachment_type=ChatAttachment.TYPE_IMAGE,
            file=image_file,
            original_filename=image_file.name,
            file_size=image_file.size,
        )

    if video_file:
        ChatAttachment.objects.create(
            message=message,
            attachment_type=ChatAttachment.TYPE_VIDEO,
            file=video_file,
            original_filename=video_file.name,
            file_size=video_file.size,
        )

    if regular_file:
        ChatAttachment.objects.create(
            message=message,
            attachment_type=ChatAttachment.TYPE_FILE,
            file=regular_file,
            original_filename=regular_file.name,
            file_size=regular_file.size,
        )

    thread.save()
    create_message_notification(message)

    return redirect("chat:chat_room", thread_id=thread.id)


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

    UserBlock.objects.get_or_create(
        blocker=request.user,
        blocked=other_user,
    )

    messages.success(request, "User blocked.")
    return redirect("chat:chat_home")

def model_has_field(model, field_name):
    return any(field.name == field_name for field in model._meta.fields)


def get_user_display_name(user):
    if hasattr(user, "profile"):
        profile = user.profile

        if getattr(profile, "display_name", ""):
            return profile.display_name

        if getattr(profile, "name", ""):
            return profile.name

    return user.get_full_name() or user.username


def create_chat_report_staff_alert(report):
    if Notification is None:
        return

    staff_users = User.objects.filter(
        is_staff=True,
        is_active=True,
    ).exclude(
        id=report.reporter_id,
    )

    channel_layer = get_channel_layer()
    reporter_name = get_user_display_name(report.reporter)

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

        allowed_data = {
            key: value
            for key, value in data.items()
            if model_has_field(Notification, key)
        }

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

@login_required
@require_POST
def report_thread_user(request, thread_id):
    thread = get_object_or_404(
        ChatThread.objects.select_related("user_one", "user_two"),
        id=thread_id,
    )

    if not thread.has_user(request.user):
        messages.error(request, "You cannot report this chat.")
        return redirect("chat:chat_home")

    reported_user = thread.other_user(request.user)

    reason = request.POST.get("reason", ChatReport.REASON_OTHER).strip()
    details = request.POST.get("details", "").strip()

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

    create_chat_report_staff_alert(report)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse(
            {
                "success": True,
                "message": "Chat reported.",
            }
        )

    messages.success(request, "Chat reported.")
    return redirect("chat:chat_room", thread.id)

@login_required
@require_POST
def delete_chat(request, thread_id):
    thread = get_object_or_404(ChatThread, id=thread_id)

    if not thread.has_user(request.user):
        messages.error(request, "This chat is not available.")
        return redirect("chat:chat_home")

    thread.delete()

    messages.success(request, "Chat deleted.")
    return redirect("chat:chat_home")