from django.conf import settings

try:
    from groq import Groq
except ImportError:
    Groq = None


def build_history_messages(history):
    """
    Convert stored HeartlyMessage objects into AI chat messages.

    These are hidden from the page, but sent to the AI so it remembers context.
    """
    messages = []

    for item in history:
        if item.role == "user":
            messages.append({
                "role": "user",
                "content": item.text,
            })

        if item.role == "ai":
            messages.append({
                "role": "assistant",
                "content": item.text,
            })

    return messages


def generate_fallback_reply(user_message: str, history=None) -> str:
    message = user_message.strip().lower()

    if not message:
        return "I am here. Type something first."

    if history:
        last_topic = None

        for item in reversed(history):
            if item.role == "user":
                last_topic = item.text
                break

        if last_topic and any(word in message for word in ["yes", "yeah", "continue", "go on", "more", "explain"]):
            return (
                f"Right, we were talking about: “{last_topic}”. "
                "Tell me what part you want to continue, and I’ll stay on that track."
            )

    if any(word in message for word in ["hello", "hi", "hey", "yo"]):
        return "Hey. I’m Heartly — friendly, useful, and only slightly dramatic. What are we doing?"

    if any(word in message for word in ["joke", "funny", "laugh"]):
        return "Why did the Django developer go outside? To get some fresh imports."

    if any(word in message for word in ["code", "django", "python", "html", "css", "bug", "error"]):
        return "Send me the error or file. I’ll help you debug it without panic-clicking everything."

    return (
        "I can help with that. Give me one more detail and tell me what you want: "
        "an explanation, advice, a plan, a rewrite, or a funny answer."
    )


def generate_heartly_reply(user_message: str, history=None) -> str:
    user_message = user_message.strip()
    history = history or []

    if not user_message:
        return "I am here. Type something first."

    if Groq is None:
        return generate_fallback_reply(user_message, history)

    if not getattr(settings, "GROQ_API_KEY", ""):
        return generate_fallback_reply(user_message, history)

    try:
        client = Groq(api_key=settings.GROQ_API_KEY)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are Heartly AI, a friendly, funny, helpful in-app assistant. "
                    "You can help with general questions, coding, school, app ideas, writing, feelings, "
                    "daily planning, and casual conversation. "
                    "You should remember the conversation context from the previous messages provided. "
                    "Do not restart the conversation unless the user clearly changes topic. "
                    "Keep replies clear, natural, friendly, practical, and lightly funny when appropriate. "
                    "Do not act like you only give dating advice. "
                    "If the user asks a follow-up like 'continue', 'what about that', 'explain more', "
                    "or 'yes', infer the topic from the previous messages."
                ),
            }
        ]

        messages.extend(build_history_messages(history))

        messages.append({
            "role": "user",
            "content": user_message,
        })

        completion = client.chat.completions.create(
            model=getattr(settings, "GROQ_MODEL", "openai/gpt-oss-20b"),
            messages=messages,
            temperature=0.75,
            max_tokens=450,
        )

        return completion.choices[0].message.content.strip()

    except Exception as error:
        print("Groq error:", error)

        return (
            "My big AI brain tripped over a cable for a second. "
            "Try again — I’m still here."
        )