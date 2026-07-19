from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.cache import patch_cache_control, patch_vary_headers

from .email_verification import current_email_is_verified
from .identity import identity_repair_issues
from .models import Profile


PROTECTED_NAMESPACES = frozenset(
    {
        "ai_features",
        "chat",
        "feed",
        "matches",
        "notifications",
        "profiles",
    }
)

# These views already enforce identity eligibility themselves, or must remain
# reachable so a user can repair an incomplete identity.
SELF_GATED_OR_EXEMPT_VIEWS = frozenset(
    {
        "matches:discover",
        "matches:swipe",
        "profiles:repair_identity",
    }
)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _private_response(response):
    patch_cache_control(
        response,
        no_cache=True,
        no_store=True,
        must_revalidate=True,
        private=True,
        max_age=0,
    )
    patch_vary_headers(response, ("Cookie",))
    return response


class AdultIdentityRequiredMiddleware:
    """Protect social routes with adult-identity and email gates."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        enforce_adult_identity = (
            settings.HEARTLY_ENFORCE_ADULT_IDENTITY
        )
        enforce_verified_email = (
            settings.HEARTLY_REQUIRE_VERIFIED_EMAIL
        )

        if not enforce_adult_identity and not enforce_verified_email:
            return None

        match = request.resolver_match

        if not match or match.namespace not in PROTECTED_NAMESPACES:
            return None

        if match.view_name in SELF_GATED_OR_EXEMPT_VIEWS:
            return None

        user = request.user

        if not user.is_authenticated:
            return _private_response(
                redirect_to_login(
                    request.get_full_path(),
                    login_url=settings.LOGIN_URL,
                )
            )

        if user.is_staff:
            return None

        if enforce_adult_identity:
            profile = Profile.objects.filter(user_id=user.pk).first()

            if identity_repair_issues(user, profile):
                repair_url = reverse("profiles:repair_identity")

                if request.method not in SAFE_METHODS:
                    return _private_response(
                        JsonResponse(
                            {
                                "ok": False,
                                "error": (
                                    "Complete your adult identity details "
                                    "before using this Heartly feature."
                                ),
                                "repair_url": repair_url,
                            },
                            status=403,
                        )
                    )

                query = urlencode({"next": request.get_full_path()})
                return _private_response(
                    redirect(f"{repair_url}?{query}")
                )

        if (
            enforce_verified_email
            and not current_email_is_verified(user)
        ):
            verification_url = reverse("settings_account")

            if request.method not in SAFE_METHODS:
                return _private_response(
                    JsonResponse(
                        {
                            "ok": False,
                            "error": (
                                "Verify your current email before using "
                                "this Heartly feature."
                            ),
                            "verification_url": verification_url,
                        },
                        status=403,
                    )
                )

            return _private_response(redirect(verification_url))

        return None
