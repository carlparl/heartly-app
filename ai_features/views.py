from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def ai_coach_page(request):
    user_message = ""
    ai_response = ""

    if request.method == "POST":
        user_message = request.POST.get("message", "").strip()

        if user_message:
            ai_response = (
                "I hear you. Here is a stronger way to approach this:\n\n"
                "1. Be clear about what you want to say.\n"
                "2. Keep the message respectful and simple.\n"
                "3. Do not force the conversation.\n"
                "4. Ask one open question so the other person can respond naturally.\n\n"
                "Example:\n"
                "“Hey, I liked your profile. You seem interesting. What’s something you enjoy doing when you’re free?”"
            )

    return render(
        request,
        "ai_features/ai_coach.html",
        {
            "user_message": user_message,
            "ai_response": ai_response,
        },
    )