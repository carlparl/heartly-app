from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.cache import patch_cache_control, patch_vary_headers

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
    """Protect Heartly's social surfaces with one consistent identity gate."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not settings.HEARTLY_ENFORCE_ADULT_IDENTITY:
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

        profile = Profile.objects.filter(user_id=user.pk).first()

        if not identity_repair_issues(user, profile):
            return None

        repair_url = reverse("profiles:repair_identity")

        if request.method not in SAFE_METHODS:
            return _private_response(
                JsonResponse(
                    {
                        "ok": False,
                        "error": (
                            "Complete your adult identity details before "
                            "using this Heartly feature."
                        ),
                        "repair_url": repair_url,
                    },
                    status=403,
                )
            )

        query = urlencode({"next": request.get_full_path()})
        return _private_response(redirect(f"{repair_url}?{query}"))
