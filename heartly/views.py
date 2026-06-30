from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


def welcome(request):
    if request.user.is_authenticated:
        return redirect("/feed/")

    return render(request, "heartly/welcome.html")


@login_required
def post_login_redirect(request):
    return redirect("/feed/")


@login_required
def settings_view(request):
    return render(request, "heartly/settings.html")


@login_required
def settings_account(request):
    return render(request, "heartly/settings_account.html")


@login_required
def settings_privacy(request):
    return render(request, "heartly/settings_privacy.html")


@login_required
def settings_help(request):
    return render(request, "heartly/settings_help.html")


@login_required
def settings_about(request):
    return render(request, "heartly/settings_about.html")


@login_required
def notifications_home(request):
    return render(request, "heartly/notifications.html")


@login_required
def delete_account(request):
    if request.method == "POST":
        confirm_text = request.POST.get("confirm_text", "").strip()

        if confirm_text != "DELETE":
            messages.error(request, "Type DELETE to confirm account deletion.")
            return redirect("delete_account")

        user = request.user
        logout(request)
        user.delete()

        messages.success(request, "Your Heartly account has been deleted.")
        return redirect("welcome")

    return render(request, "heartly/delete_account.html")