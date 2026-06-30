from django.contrib import messages as django_messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .models import Conversation, Message as ChatMessage


User = get_user_model()


@login_required
def chat_home(request):
    """
    Chat list page.
    URL: /chat/
    """
    conversations = (
        Conversation.objects
        .for_user(request.user)
        .select_related("user_one", "user_two")
        .order_by("-updated_at")
    )

    conversation_items = []

    for conversation in conversations:
        other_user = conversation.get_other_user(request.user)
        last_message = conversation.get_last_message()

        unread_count = conversation.messages.filter(
            is_read=False
        ).exclude(
            sender=request.user
        ).count()

        conversation_items.append({
            "conversation": conversation,
            "other_user": other_user,
            "last_message": last_message,
            "unread_count": unread_count,
        })

    return render(
        request,
        "chat/chat_home.html",
        {
            "conversation_items": conversation_items,
        },
    )


@login_required
def chat_room(request, conversation_id):
    """
    Individual chat room.
    URL: /chat/<conversation_id>/
    """
    conversation = get_object_or_404(
        Conversation.objects.select_related("user_one", "user_two"),
        id=conversation_id,
    )

    if request.user not in [conversation.user_one, conversation.user_two]:
        django_messages.error(request, "You do not have access to this conversation.")
        return redirect("chat:chat_home")

    ChatMessage.objects.filter(
        conversation=conversation,
        is_read=False,
    ).exclude(
        sender=request.user,
    ).update(is_read=True)

    chat_messages = list(
        conversation.messages
        .select_related("sender")
        .order_by("-created_at")[:100]
    )
    chat_messages.reverse()

    other_user = conversation.get_other_user(request.user)

    return render(
        request,
        "chat/chat_room.html",
        {
            "conversation": conversation,
            "other_user": other_user,
            "chat_messages": chat_messages,
        },
    )


@login_required
def start_conversation(request, user_id):
    """
    Creates or opens a conversation with another user.
    URL: /chat/start/<user_id>/
    """
    other_user = get_object_or_404(User, id=user_id)

    if other_user == request.user:
        django_messages.error(request, "You cannot start a chat with yourself.")
        return redirect("chat:chat_home")

    conversation = Conversation.objects.between(request.user, other_user)

    return redirect("chat:chat_room", conversation_id=conversation.id)