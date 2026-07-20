from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.cache import patch_cache_control, patch_vary_headers

from .moderation import account_can_access


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


class AccountModerationMiddleware:
    """Block restricted accounts across every authenticated HTTP route."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if not user.is_authenticated or account_can_access(user):
            return self.get_response(request)

        exempt_paths = {
            reverse("account_logout"),
            reverse("community_guidelines"),
            reverse("privacy_policy"),
            reverse("terms_of_service"),
            reverse("data_export"),
            reverse("delete_account"),
        }
        if request.path in exempt_paths:
            return self.get_response(request)

        status = user.active_moderation_status()
        payload = {
            "ok": False,
            "error": "This account is not currently available.",
            "moderation_status": status,
        }
        if user.moderation_expires_at:
            payload["available_after"] = (
                user.moderation_expires_at.isoformat()
            )

        wants_json = (
            request.method not in SAFE_METHODS
            or "application/json"
            in request.headers.get("Accept", "")
        )
        if wants_json:
            return _private_response(
                JsonResponse(payload, status=403)
            )

        return _private_response(
            render(
                request,
                "account/account_restricted.html",
                payload,
                status=403,
            )
        )
