from urllib.parse import urlencode
from datetime import timedelta

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from profiles.identity import identity_repair_issues
from profiles.models import Profile

from .models import EmailVerificationCode


EMAIL_CODE_COOLDOWN_SECONDS = 60
EMAIL_CODE_MAX_ATTEMPTS = 5


def _current_email_address(user):
    email = (user.email or "").strip()
    if not email:
        return None

    email_address = (
        EmailAddress.objects
        .filter(user=user, email__iexact=email)
        .first()
    )
    if email_address:
        return email_address

    return EmailAddress.objects.create(
        user=user,
        email=email,
        primary=not EmailAddress.objects.filter(
            user=user,
            primary=True,
        ).exists(),
        verified=False,
    )


def _email_is_verified(user):
    email_address = _current_email_address(user)
    return bool(email_address and email_address.verified)


def _sync_profile_email_verification(user):
    verified = _email_is_verified(user)
    profile, _ = Profile.objects.get_or_create(user=user)

    if profile.email_verified != verified:
        profile.email_verified = verified
        profile.save(
            update_fields=["email_verified", "updated_at"]
        )

    return verified


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
        repair_url = reverse("profiles:repair_identity")
        discover_url = reverse("matches:discover")
        query = urlencode({"next": discover_url})
        return redirect(f"{repair_url}?{query}")

    email_verified = _sync_profile_email_verification(
        request.user
    )

    if (
        settings.HEARTLY_REQUIRE_VERIFIED_EMAIL
        and not email_verified
    ):
        return redirect("settings_account")

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
    email_verified = _sync_profile_email_verification(
        request.user
    )

    return render(
        request,
        "accounts/settings_account.html",
        {
            "profile": _profile_for(request.user),
            "active_section": "account",
            "email_verified": email_verified,
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
    user = request.user
    email = (user.email or "").strip()

    if not email:
        messages.error(
            request,
            "Add an email address before requesting a code.",
        )
        return redirect("settings_account")

    if _email_is_verified(user):
        _sync_profile_email_verification(user)
        messages.info(
            request,
            "Your email address is already verified.",
        )
        return redirect("settings_account")

    cooldown_boundary = timezone.now() - timedelta(
        seconds=EMAIL_CODE_COOLDOWN_SECONDS
    )
    recent_code = (
        EmailVerificationCode.objects
        .filter(
            user=user,
            email=email,
            used_at__isnull=True,
            created_at__gte=cooldown_boundary,
        )
        .order_by("-created_at")
        .first()
    )
    if recent_code:
        messages.error(
            request,
            "A code was sent recently. Wait one minute before requesting another.",
        )
        return redirect("settings_account")

    verification, raw_code = (
        EmailVerificationCode.create_for_user(user)
    )

    body = (
        f"Your Heartly verification code is {raw_code}.\n\n"
        "It expires in 10 minutes and can be tried up to five times.\n"
        "If you did not request this code, ignore this email."
    )

    try:
        sent_count = send_mail(
            "Your Heartly verification code",
            body,
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )
    except Exception:
        verification.mark_used()
        messages.error(
            request,
            "Heartly could not send the verification email. Try again later.",
        )
        return redirect("settings_account")

    if sent_count != 1:
        verification.mark_used()
        messages.error(
            request,
            "Heartly could not send the verification email. Try again later.",
        )
        return redirect("settings_account")

    messages.success(
        request,
        "A six-digit verification code was sent to your email.",
    )
    return redirect("settings_account")


@login_required
@require_POST
def verify_email_code(request):
    user = request.user
    email = (user.email or "").strip()
    raw_code = (request.POST.get("code", "") or "").strip()

    if not (len(raw_code) == 6 and raw_code.isdigit()):
        messages.error(
            request,
            "Enter the six-digit verification code.",
        )
        return redirect("settings_account")

    verification = (
        EmailVerificationCode.objects
        .filter(
            user=user,
            email=email,
            used_at__isnull=True,
        )
        .order_by("-created_at")
        .first()
    )

    if verification is None:
        messages.error(
            request,
            "Request a new verification code first.",
        )
        return redirect("settings_account")

    if verification.is_expired():
        verification.mark_used()
        messages.error(
            request,
            "That verification code has expired. Request a new code.",
        )
        return redirect("settings_account")

    if not verification.can_attempt():
        messages.error(
            request,
            "That verification code can no longer be used. Request a new code.",
        )
        return redirect("settings_account")

    if not verification.check_code(raw_code):
        remaining_attempts = max(
            EMAIL_CODE_MAX_ATTEMPTS - verification.attempts,
            0,
        )
        suffix = "" if remaining_attempts == 1 else "s"
        messages.error(
            request,
            (
                "Incorrect verification code. "
                f"{remaining_attempts} attempt{suffix} remaining."
            ),
        )
        return redirect("settings_account")

    with transaction.atomic():
        verification.mark_used()

        email_address = _current_email_address(user)
        EmailAddress.objects.filter(
            user=user,
            primary=True,
        ).exclude(pk=email_address.pk).update(primary=False)

        email_address.email = email
        email_address.primary = True
        email_address.verified = True
        email_address.save(
            update_fields=["email", "primary", "verified"]
        )

        Profile.objects.filter(user=user).update(
            email_verified=True,
            updated_at=timezone.now(),
        )

        EmailVerificationCode.objects.filter(
            user=user,
            email=email,
            used_at__isnull=True,
        ).exclude(pk=verification.pk).update(
            used_at=timezone.now()
        )

    messages.success(
        request,
        "Your email address is now verified.",
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

    return render(request, "accounts/delete_account.html")
