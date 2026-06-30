from django.conf import settings
from groq import Groq

from .models import GropConversation, GropMessage, GropUserMemory


HEARTLY_SYSTEM_PROMPT = """
You are Heartly, the friendly AI coach inside the Heartly dating app.

Your role:
- Help users improve their dating profiles.
- Help users write first messages.
- Help users reply naturally.
- Help users build confidence.
- Help users think through safe, respectful dating choices.

Personality:
- Friendly, casual, warm, and welcoming.
- Sound like a supportive coach, not a robot.
- Keep replies short and useful.
- Ask at most one follow-up question.
- Use simple language.
- Never be creepy, pushy, or judgmental.
- Never pretend to be human.
- Never claim you remember something unless stored context is provided.

Safety:
- Encourage respectful communication.
- Encourage public first meetings, telling someone trusted, and avoiding pressure.
- If a user describes danger, harassment, abuse, coercion, or threats, encourage them to seek trusted local help and prioritize safety.
"""


def get_active_conversation(user):
    conversation, _ = GropConversation.objects.get_or_create(
        user=user,
        is_active=True,
        defaults={"title": "Chat with Heartly"},
    )
    return conversation


def get_user_memory(user):
    memory, _ = GropUserMemory.objects.get_or_create(user=user)
    return memory


def build_messages_for_groq(user, conversation):
    memory = get_user_memory(user)

    recent_messages = conversation.messages.order_by("-created_at")[:12]
    recent_messages = list(reversed(recent_messages))

    messages = [
        {
            "role": "system",
            "content": HEARTLY_SYSTEM_PROMPT,
        }
    ]

    if memory.memory_enabled:
        messages.append({
            "role": "system",
            "content": (
                "Stored user context:\n"
                f"Preferences: {memory.preference_notes or 'None yet'}\n"
                f"Previous chat summary: {memory.last_context_summary or conversation.summary or 'None yet'}"
            ),
        })

    for message in recent_messages:
        if message.role in ["user", "assistant"]:
            messages.append({
                "role": message.role,
                "content": message.content,
            })

    return messages


def generate_heartly_reply(user, conversation):
    if not getattr(settings, "GROQ_API_KEY", ""):
        return (
            "Hey, I’m Heartly 👋 I’m ready to help, but the Groq API key is not configured yet. "
            "Add GROQ_API_KEY and restart the server."
        )

    client = Groq(api_key=settings.GROQ_API_KEY)

    response = client.chat.completions.create(
        model=getattr(settings, "GROQ_MODEL", "llama-3.1-8b-instant"),
        messages=build_messages_for_groq(user, conversation),
        temperature=getattr(settings, "HEARTLY_AI_TEMPERATURE", 0.7),
        max_completion_tokens=getattr(settings, "HEARTLY_AI_MAX_TOKENS", 350),
    )

    return response.choices[0].message.content.strip()


def update_memory(user, conversation):
    memory = get_user_memory(user)

    if not memory.memory_enabled:
        return

    last_messages = conversation.messages.order_by("-created_at")[:10]
    last_messages = list(reversed(last_messages))

    summary_parts = []

    for message in last_messages:
        text = message.content.strip()

        if not text:
            continue

        if len(text) > 150:
            text = text[:150] + "..."

        label = "User" if message.role == "user" else "Heartly"
        summary_parts.append(f"{label}: {text}")

    memory.last_context_summary = "\n".join(summary_parts)
    memory.save(update_fields=["last_context_summary", "updated_at"])


def run_ai_coach_chat(user, message):
    conversation = get_active_conversation(user)

    GropMessage.objects.create(
        conversation=conversation,
        role=GropMessage.ROLE_USER,
        content=message,
    )

    reply = generate_heartly_reply(user, conversation)

    GropMessage.objects.create(
        conversation=conversation,
        role=GropMessage.ROLE_ASSISTANT,
        content=reply,
    )

    update_memory(user, conversation)

    return reply


def run_ai_tool(user, prompt):
    return run_ai_coach_chat(user, prompt)