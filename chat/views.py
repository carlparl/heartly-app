from pathlib import Path

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.apps import apps
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from profiles.blocking import user_is_hidden_for
from profiles.models import Profile, UserBlock

from .models import (
    CallSession,
    ChatAttachment,
    ChatMessage,
    ChatReport,
    ChatThread,
)

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

MAX_IMAGE_SIZE = 8 * 1024 * 1024
MAX_VIDEO_SIZE = 50 * 1024 * 1024
MAX_FILE_SIZE = 25 * 1024 * 1024
MAX_AUDIO_SIZE = 15 * 1024 * 1024

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
    ".m4v",
    ".3gp",
    ".3g2",
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

ALLOWED_AUDIO_EXTENSIONS = {
    ".webm",
    ".ogg",
    ".mp3",
    ".mp4",
    ".m4a",
    ".wav",
    ".aac",
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
    if not uploaded_file:
        return "No file was selected."

    if uploaded_file.size <= 0:
        return "File is empty. Please record or select the file again."

    if uploaded_file.size < 1500:
        return "Voice note is too short or empty. Please record again."

    content_type = (uploaded_file.content_type or "").lower()
    extension = Path(uploaded_file.name or "").suffix.lower()

    if content_type not in allowed_types and extension not in allowed_extensions:
        return "File type not supported."

    if uploaded_file.size > max_size:
        return "File is too large."

    return None


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
    
    if attachment.attachment_type == ChatAttachment.TYPE_AUDIO:
        return f"{prefix}Voice note"

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
    voice_file = request.FILES.get("voice") or request.FILES.get("audio")

    if not text and not image_file and not video_file and not regular_file and not voice_file:
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

    if voice_file:
        error = validate_upload(
            voice_file,
            ALLOWED_AUDIO_TYPES,
            ALLOWED_AUDIO_EXTENSIONS,
            MAX_AUDIO_SIZE,
        )

        if error:
            messages.error(request, error)
            return redirect("chat:chat_room", thread_id=thread.id)

    message = ChatMessage.objects.create(
    thread=thread,
    sender=request.user,
    text=text,
)

    try:
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

        if voice_file:
            ChatAttachment.objects.create(
                message=message,
                attachment_type=ChatAttachment.TYPE_AUDIO,
                file=voice_file,
                original_filename=voice_file.name or "heartly-voice-note.webm",
                file_size=voice_file.size,
            )

    except Exception as exc:
        message.delete()

        if settings.DEBUG:
            messages.error(request, f"Upload failed: {exc}")
        else:
            messages.error(request, "Upload failed. Please try again.")

        return redirect("chat:chat_room", thread_id=thread.id)

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

    call_url = reverse("chat:call_room", args=[call.id])
    channel_layer = get_channel_layer()

    if channel_layer:
        try:
            async_to_sync(channel_layer.group_send)(
                f"heartly_user_{other_user.id}",
                {
                    "type": "notification.event",
                    "payload": {
                        "type": "incoming_call",
                        "call_id": call.id,
                        "thread_id": thread.id,
                        "call_type": call.call_type,
                        "caller_id": request.user.id,
                        "receiver_id": other_user.id,
                        "caller_name": get_display_name(request.user),
                        "url": call_url,
                        "accept_url": call_url,
                    },
                },
            )
        except Exception:
            pass

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
        messages.error(request, "Only the receiver can accept this call.")
        return redirect("chat:chat_room", thread_id=call.thread.id)

    if call.status == CallSession.STATUS_RINGING:
        call.status = CallSession.STATUS_ACCEPTED
        call.accepted_at = timezone.now()
        call.save(update_fields=["status", "accepted_at"])

    return redirect("chat:call_room", call_id=call.id)


@login_required
@require_POST
def decline_call(request, call_id):
    call = get_object_or_404(
        CallSession.objects.select_related("thread", "caller", "receiver"),
        id=call_id,
    )

    if request.user not in [call.caller, call.receiver]:
        messages.error(request, "You do not have access to this call.")
        return redirect("chat:chat_home")

    call.status = CallSession.STATUS_DECLINED
    call.ended_at = timezone.now()
    call.save(update_fields=["status", "ended_at"])

    return redirect("chat:chat_room", thread_id=call.thread.id)


@login_required
@require_POST
def end_call(request, call_id):
    call = get_object_or_404(
        CallSession.objects.select_related("thread", "caller", "receiver"),
        id=call_id,
    )

    if request.user not in [call.caller, call.receiver]:
        messages.error(request, "You do not have access to this call.")
        return redirect("chat:chat_home")

    call.status = CallSession.STATUS_ENDED
    call.ended_at = timezone.now()
    call.save(update_fields=["status", "ended_at"])

    return redirect("chat:chat_room", thread_id=call.thread.id)


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

    if model_has_field(instance.__class__, "hidden_at"):
        instance.hidden_at = timezone.now()
        changed.append("hidden_at")

    if model_has_field(instance.__class__, "deleted_at"):
        instance.deleted_at = timezone.now()
        changed.append("deleted_at")

    if model_has_field(instance.__class__, "cleared_at"):
        instance.cleared_at = timezone.now()
        changed.append("cleared_at")

    if changed:
        instance.save(update_fields=list(dict.fromkeys(changed)))

    return bool(changed)


def hide_messages_for_user(thread, user, message_ids=None):
    MessageState = optional_chat_model("ChatMessageUserState")

    qs = ChatMessage.objects.filter(thread=thread)

    if message_ids is not None:
        qs = qs.filter(id__in=message_ids)

    if MessageState is None:
        return qs.delete()[0]

    count = 0

    for message in qs:
        state, created = MessageState.objects.get_or_create(
            message=message,
            user=user,
        )

        changed = set_available_boolean_fields(
            state,
            [
                "hidden_for_me",
                "deleted_for_me",
                "is_hidden",
                "is_deleted",
                "is_cleared",
            ],
        )

        if not changed:
            state.save()

        count += 1

    return count


@login_required
@require_POST
def clear_chat_for_me(request, thread_id):
    thread = get_object_or_404(ChatThread, id=thread_id)

    if not thread.has_user(request.user):
        messages.error(request, "This chat is not available.")
        return redirect("chat:chat_home")

    ThreadState = optional_chat_model("ChatThreadUserState")

    if ThreadState is not None:
        state, created = ThreadState.objects.get_or_create(
            thread=thread,
            user=request.user,
        )

        set_available_boolean_fields(
            state,
            [
                "cleared_for_me",
                "hidden_for_me",
                "deleted_for_me",
                "is_cleared",
                "is_hidden",
                "is_deleted",
            ],
        )

    hidden_count = hide_messages_for_user(thread, request.user)

    messages.success(request, "Chat cleared." if hidden_count else "Chat is already clear.")
    return redirect("chat:chat_room", thread_id=thread.id)


@login_required
@require_POST
def delete_chat_for_me(request, thread_id):
    thread = get_object_or_404(ChatThread, id=thread_id)

    if not thread.has_user(request.user):
        messages.error(request, "This chat is not available.")
        return redirect("chat:chat_home")

    ThreadState = optional_chat_model("ChatThreadUserState")

    if ThreadState is not None:
        state, created = ThreadState.objects.get_or_create(
            thread=thread,
            user=request.user,
        )
        set_available_boolean_fields(
            state,
            [
                "deleted_for_me",
                "hidden_for_me",
                "is_deleted",
                "is_hidden",
            ],
        )
        hide_messages_for_user(thread, request.user)
        messages.success(request, "Chat deleted for you.")
        return redirect("chat:chat_home")

    thread.delete()
    messages.success(request, "Chat deleted.")
    return redirect("chat:chat_home")


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
    selected_ids = request.POST.getlist("message_ids")
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or reverse("chat:chat_home")

    if not selected_ids:
        messages.error(request, "Select at least one message.")
        return redirect(next_url)

    messages_qs = ChatMessage.objects.filter(
        id__in=selected_ids,
    ).filter(
        Q(thread__user_one=request.user) | Q(thread__user_two=request.user)
    )

    grouped = {}
    for message in messages_qs.select_related("thread"):
        grouped.setdefault(message.thread, []).append(message.id)

    deleted_count = 0
    for thread, message_ids in grouped.items():
        deleted_count += hide_messages_for_user(thread, request.user, message_ids)

    if deleted_count:
        messages.success(request, "Selected messages deleted for you.")
    else:
        messages.error(request, "No valid messages selected.")

    return redirect(next_url)


@login_required
@require_POST
def delete_selected_messages_for_everyone(request):
    selected_ids = request.POST.getlist("message_ids")
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or reverse("chat:chat_home")

    if not selected_ids:
        messages.error(request, "Select at least one message.")
        return redirect(next_url)

    qs = ChatMessage.objects.filter(
        id__in=selected_ids,
        sender=request.user,
    ).filter(
        Q(thread__user_one=request.user) | Q(thread__user_two=request.user)
    )

    soft_fields = [
        "deleted_for_everyone",
        "is_deleted_for_everyone",
        "is_deleted",
    ]

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
    thread = get_object_or_404(ChatThread, id=thread_id)

    if not thread.has_user(request.user):
        messages.error(request, "This chat is not available.")
        return redirect("chat:chat_home")

    thread.delete()

    messages.success(request, "Chat deleted.")
    return redirect("chat:chat_home")
