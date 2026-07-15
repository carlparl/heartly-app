from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import (
    require_http_methods,
    require_POST,
)

from profiles.identity import identity_repair_issues
from profiles.models import Profile


def welcome(request):
    if request.user.is_authenticated:
        return redirect("post_login_redirect")

    return render(request, "welcome.html")


@login_required
def post_login_redirect(request):
    profile, _ = Profile.objects.get_or_create(
        user=request.user
    )

    if request.user.is_staff:
        return redirect("feed:feed_home")

    if identity_repair_issues(request.user, profile):
        repair_url = reverse(
            "profiles:repair_identity"
        )
        discover_url = reverse("matches:discover")
        query = urlencode({"next": discover_url})

        return redirect(f"{repair_url}?{query}")

    return redirect("matches:discover")


def _profile_for(user):
    profile, _ = Profile.objects.get_or_create(user=user)
    return profile


@login_required
def settings_home(request):
    return render(
        request,
        "accounts/settings.html",
        {
            "profile": _profile_for(request.user),
            "active_section": "home",
        },
    )


@login_required
def settings_view(request):
    return settings_home(request)


@login_required
def settings_account(request):
    return render(
        request,
        "accounts/settings_account.html",
        {
            "profile": _profile_for(request.user),
            "active_section": "account",
        },
    )


@login_required
def settings_privacy(request):
    return redirect("settings")


@login_required
def notifications_home(request):
    return redirect("settings")


@login_required
def settings_help(request):
    return redirect("settings")


@login_required
def settings_about(request):
    return redirect("settings")


@login_required
@require_POST
def send_email_code(request):
    messages.info(
        request,
        "Email verification code sending is not configured yet.",
    )
    return redirect("settings_account")


@login_required
@require_POST
def verify_email_code(request):
    messages.info(
        request,
        "Email verification is not configured yet.",
    )
    return redirect("settings_account")


@login_required
@require_http_methods(["GET", "POST"])
def delete_account(request):
    user = request.user

    if request.method == "POST":
        password = request.POST.get("password", "")
        confirm_delete = request.POST.get(
            "confirm_delete",
            "",
        ).strip()

        if confirm_delete != "DELETE":
            messages.error(
                request,
                "Type DELETE exactly to confirm account deletion.",
            )
            return redirect("delete_account")

        if (
            user.has_usable_password()
            and not user.check_password(password)
        ):
            messages.error(
                request,
                "Incorrect password. Account was not deleted.",
            )
            return redirect("delete_account")

        logout(request)
        user.delete()

        messages.success(
            request,
            "Your Heartly account has been deleted.",
        )
        return redirect("welcome")

    return render(
        request,
        "accounts/delete_account.html",
    )
