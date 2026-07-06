from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .models import HeartlyMessage
from .services import generate_heartly_reply


@login_required
def ai_coach_page(request):
    """
    Open clean every time.

    We do NOT display stored messages.
    Stored messages are only used as hidden context for the AI.
    """
    return render(request, "ai_features/ai_coach.html")


@login_required
@require_POST
def ai_coach_send(request):
    user_text = request.POST.get("message", "").strip()

    if not user_text:
        return JsonResponse({
            "ok": False,
            "reply": "Type something first."
        })

    # Get recent memory BEFORE saving the new message.
    recent_messages = list(
        HeartlyMessage.objects
        .filter(user=request.user)
        .order_by("-created_at")[:12]
    )

    recent_messages.reverse()

    # Store user's new message.
    HeartlyMessage.objects.create(
        user=request.user,
        role="user",
        text=user_text,
    )

    # Generate reply using hidden memory.
    ai_reply = generate_heartly_reply(
        user_message=user_text,
        history=recent_messages,
    )

    # Store Heartly's reply.
    HeartlyMessage.objects.create(
        user=request.user,
        role="ai",
        text=ai_reply,
    )

    return JsonResponse({
        "ok": True,
        "reply": ai_reply,
    })


@login_required
@require_POST
def ai_coach_end_chat(request):
    """
    Clear only the visible frontend chat.

    Stored messages remain in database so Heartly can still remember context.
    """
    return JsonResponse({
        "ok": True,
        "reply": "New chat started. What do you want to talk about?",
    })