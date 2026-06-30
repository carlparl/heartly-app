from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import InterestForm, ProfileForm
from .models import Interest, Profile


DEFAULT_INTERESTS = [
    "Music",
    "Movies",
    "Travel",
    "Anime"
    "Food",
    "Sports",
    "Art",
    "Gaming",
    "Reading",
    "Fitness",
    "Tech",
]


def ensure_default_interests():
    for name in DEFAULT_INTERESTS:
        Interest.objects.get_or_create(name=name)


@login_required
def profile_home(request):
    profile, created = Profile.objects.get_or_create(user=request.user)

    return render(
        request,
        "profiles/profile.html",
        {
            "profile": profile,
        },
    )


@login_required
def edit_profile(request):
    profile, created = Profile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=profile)

        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("profiles:profile_home")
    else:
        form = ProfileForm(instance=profile)

    return render(
        request,
        "profiles/edit_profile.html",
        {
            "form": form,
            "profile": profile,
        },
    )


@login_required
def edit_interests(request):
    ensure_default_interests()

    profile, created = Profile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = InterestForm(request.POST, instance=profile)

        if form.is_valid():
            form.save()
            messages.success(request, "Interests updated.")
            return redirect("profiles:profile_home")
    else:
        form = InterestForm(instance=profile)

    return render(
        request,
        "profiles/interests.html",
        {
            "form": form,
            "profile": profile,
        },
    )