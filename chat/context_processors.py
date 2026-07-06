from django.db.models import Q

from .models import ChatMessage, ChatThread


try:
    from profiles.blocking import hidden_user_ids_for
except Exception:
    hidden_user_ids_for = None


def unread_chat_messages(request):
    if not request.user.is_authenticated:
        return {
            "unread_chat_messages_count": 0,
        }

    hidden_ids = hidden_user_ids_for(request.user) if hidden_user_ids_for else set()

    threads = (
        ChatThread.objects
        .filter(Q(user_one=request.user) | Q(user_two=request.user))
        .exclude(user_one_id__in=hidden_ids)
        .exclude(user_two_id__in=hidden_ids)
    )

    unread_count = (
        ChatMessage.objects
        .filter(thread__in=threads, is_read=False)
        .exclude(sender=request.user)
        .count()
    )

    return {
        "unread_chat_messages_count": unread_count,
    }
