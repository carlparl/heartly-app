from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required


def welcome(request):
    """
    Root page: http://127.0.0.1:8000/

    This page always shows the auth landing screen.
    Logged-out users see Sign Up and Login.
    Logged-in users see Continue to Discover and Logout.
    """
    return render(request, "heartly/welcome.html")


@login_required
def post_login_redirect(request):
    """
    Runs only after successful login/signup.
    """
    return redirect("matches:discover")
@login_required
def settings_view(request):
    return render(request, "accounts/settings.html")