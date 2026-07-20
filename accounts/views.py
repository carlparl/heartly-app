from urllib.parse import urlencode
from datetime import timedelta

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from profiles.identity import identity_repair_issues
from profiles.models import Profile

from .data_export import build_user_data_export
from .models import CustomUser, EmailVerificationCode


EMAIL_CODE_MAX_ATTEMPTS = 5


POLICY_PAGES = {
    "community_guidelines": {
        "title": "Community Guidelines",
        "intro": (
            "Heartly is an adults-only community built around "
            "respect, honesty, privacy, and safer interaction."
        ),
        "sections": [
            (
                "Adults only",
                "Accounts are limited to people aged 18 or older. "
                "Identity information must be accurate.",
            ),
            (
                "Respect and boundaries",
                "Do not harass, threaten, pressure, impersonate, "
                "or target other members.",
            ),
            (
                "Authentic participation",
                "Do not use scams, spam, deceptive profiles, or "
                "misleading content.",
            ),
            (
                "Privacy and reporting",
                "Protect personal information. Use Heartly's block "
                "and report tools when something feels unsafe.",
            ),
            (
                "Enforcement",
                "Heartly may hide content, restrict accounts, or "
                "preserve report evidence for safety review.",
            ),
        ],
    },
    "privacy_policy": {
        "title": "Privacy Policy",
        "intro": (
            "This summary explains how Heartly uses and protects "
            "account, profile, activity, and safety information."
        ),
        "sections": [
            (
                "Information collected",
                "Heartly stores account details, profile content, "
                "connection activity, messages, and safety reports.",
            ),
            (
                "How information is used",
                "Information supports account access, matching, "
                "communication, security, and moderation.",
            ),
            (
                "Visibility and control",
                "Profile and privacy settings control what other "
                "members can see where the feature allows it.",
            ),
            (
                "Safety retention",
                "Bounded report evidence may be retained so staff can "
                "review reports even if content later changes.",
            ),
            (
                "Account choices",
                "Members can manage settings and request account "
                "deletion, subject to lawful safety retention needs.",
            ),
        ],
    },
    "terms_of_service": {
        "title": "Terms of Service",
        "intro": (
            "These terms describe the basic rules for using Heartly."
        ),
        "sections": [
            (
                "Eligibility",
                "You must be at least 18 and provide accurate account "
                "and identity information.",
            ),
            (
                "Acceptable use",
                "Use Heartly lawfully and follow the Community "
                "Guidelines and safety controls.",
            ),
            (
                "Your content",
                "You remain responsible for content you submit and "
                "must have permission to share it.",
            ),
            (
                "Safety actions",
                "Heartly may review reports, hide content, suspend or "
                "ban accounts, and keep an audit history.",
            ),
            (
                "Service changes",
                "Features may change as Heartly improves reliability, "
                "privacy, and safety.",
            ),
        ],
    },
}


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


def _reserve_email_verification_code(user, email):
    """Atomically reserve one send slot and create its code."""
    now = timezone.now()

    with transaction.atomic():
        locked_user = (
            CustomUser.objects
            .select_for_update()
            .get(pk=user.pk)
        )
        locked_email = (locked_user.email or "").strip()

        if locked_email.casefold() != email.casefold():
            return None, None, "email_changed"

        codes = EmailVerificationCode.objects.filter(
            user=locked_user,
            email__iexact=locked_email,
        )

        cooldown_boundary = now - timedelta(
            seconds=(
                settings.HEARTLY_EMAIL_CODE_COOLDOWN_SECONDS
            )
        )
        if codes.filter(
            created_at__gte=cooldown_boundary
        ).exists():
            return None, None, "cooldown"

        hourly_boundary = now - timedelta(hours=1)
        hourly_count = codes.filter(
            created_at__gte=hourly_boundary
        ).count()
        if (
            hourly_count
            >= settings.HEARTLY_EMAIL_CODE_MAX_SENDS_PER_HOUR
        ):
            return None, None, "hourly"

        daily_boundary = now - timedelta(days=1)
        daily_count = codes.filter(
            created_at__gte=daily_boundary
        ).count()
        if (
            daily_count
            >= settings.HEARTLY_EMAIL_CODE_MAX_SENDS_PER_DAY
        ):
            return None, None, "daily"

        verification, raw_code = (
            EmailVerificationCode.create_for_user(
                locked_user
            )
        )

    return verification, raw_code, None


def welcome(request):
    if request.user.is_authenticated:
        return redirect("post_login_redirect")
    return render(request, "welcome.html")


def _render_policy(request, policy_name):
    return render(
        request,
        "account/policy_page.html",
        POLICY_PAGES[policy_name],
    )


def community_guidelines(request):
    return _render_policy(request, "community_guidelines")


def privacy_policy(request):
    return _render_policy(request, "privacy_policy")


def terms_of_service(request):
    return _render_policy(request, "terms_of_service")


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
@require_http_methods(["GET", "POST"])
def data_export(request):
    if request.method == "GET":
        return render(request, "accounts/data_export.html")

    confirm_export = request.POST.get(
        "confirm_export",
        "",
    ).strip()
    password = request.POST.get("password", "")

    if confirm_export != "EXPORT":
        messages.error(
            request,
            "Type EXPORT exactly to create your data file.",
        )
        return redirect("data_export")

    if (
        request.user.has_usable_password()
        and not request.user.check_password(password)
    ):
        messages.error(
            request,
            "Incorrect password. No data file was created.",
        )
        return redirect("data_export")

    export = build_user_data_export(request.user)
    response = JsonResponse(
        export,
        json_dumps_params={"indent": 2, "sort_keys": True},
    )
    response["Content-Disposition"] = (
        'attachment; filename="heartly-account-data.json"'
    )
    response["Cache-Control"] = "no-store, private"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    return response


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

    verification, raw_code, limit_reason = (
        _reserve_email_verification_code(user, email)
    )

    if limit_reason == "cooldown":
        messages.error(
            request,
            "A code was sent recently. Wait one minute before requesting another.",
        )
        return redirect("settings_account")

    if limit_reason == "email_changed":
        messages.error(
            request,
            "Your email address changed. Refresh the page and try again.",
        )
        return redirect("settings_account")

    if limit_reason:
        messages.error(
            request,
            "Too many verification emails were requested. Try again later.",
        )
        return redirect("settings_account")

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
