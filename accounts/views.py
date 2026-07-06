from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from profiles.models import Profile


def welcome(request):
    if request.user.is_authenticated:
        return redirect("feed:feed_home")

    return render(request, "welcome.html")


@login_required
def post_login_redirect(request):
    Profile.objects.get_or_create(user=request.user)

    return redirect("feed:feed_home")


@login_required
def settings_view(request):
    profile, created = Profile.objects.get_or_create(user=request.user)

    return render(
        request,
        "accounts/settings.html",
        {
            "profile": profile,
        },
    )


@login_required
def settings_help(request):
    return settings_view(request)