import logging
import re
import secrets
import time
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import logout
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from .security import consume_rate_limit, request_identity


request_logger = logging.getLogger("heartly.request")
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


SESSION_CREATED_KEY = "heartly_session_created_at"
SESSION_ACTIVITY_KEY = "heartly_session_activity_at"


RATE_LIMIT_VIEW_GROUPS = {
    "account_login": "auth_login",
    "account_signup": "auth_signup",
    "account_reset_password": "auth_recovery",
    "account_reset_password_from_key": "auth_recovery",
    "send_email_code": "email_verification",
    "verify_email_code": "email_verification",
    "delete_account": "sensitive_account",
    "profiles:report_profile": "reports",
    "feed:report_post": "reports",
    "chat:report_thread_user": "reports",
    "profiles:block_user": "blocking",
    "profiles:unblock_user": "blocking",
    "chat:block_thread_user": "blocking",
    "matches:swipe": "swipes",
    "chat:send_message": "messages",
    "feed:create_post": "feed_writes",
    "feed:create_story": "feed_writes",
    "feed:react_story": "feed_writes",
    "feed:like_post": "feed_writes",
    "feed:react_post": "feed_writes",
    "feed:toggle_like": "feed_writes",
    "feed:save_post": "feed_writes",
    "feed:comment_post": "feed_writes",
    "feed:add_comment": "feed_writes",
    "feed:reply_comment": "feed_writes",
    "feed:react_comment": "feed_writes",
    "chat:start_call": "call_controls",
    "chat:accept_call": "call_controls",
    "chat:decline_call": "call_controls",
    "chat:end_call": "call_controls",
    "chat:miss_call": "call_controls",
    "profiles:edit_profile": "profile_writes",
    "profiles:repair_identity": "profile_writes",
    "profiles:edit_interests": "profile_writes",
    "profiles:toggle_profile_visibility": "profile_writes",
    "profiles:toggle_online_status": "profile_writes",
    "profiles:toggle_message_requests": "profile_writes",
    "profiles:toggle_safety_filters": "profile_writes",
}


def wants_json(request):
    return (
        request.headers.get("x-requested-with")
        == "XMLHttpRequest"
        or "application/json"
        in request.headers.get("accept", "").lower()
    )


def add_security_headers(response):
    response.setdefault(
        "Referrer-Policy",
        "strict-origin-when-cross-origin",
    )
    response.setdefault(
        "Permissions-Policy",
        "camera=(self), microphone=(self), geolocation=()",
    )
    response.setdefault(
        "X-Permitted-Cross-Domain-Policies",
        "none",
    )
    return response


def no_store(response):
    response["Cache-Control"] = (
        "no-store, no-cache, max-age=0, must-revalidate, private"
    )
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.META.get("HTTP_X_REQUEST_ID", "")
        request_id = (
            incoming
            if SAFE_REQUEST_ID.fullmatch(incoming)
            else secrets.token_hex(16)
        )
        request.heartly_request_id = request_id
        started = time.monotonic()

        response = self.get_response(request)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        response["X-Request-ID"] = request_id

        log_fields = {
            "request_id": request_id,
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "elapsed_ms": elapsed_ms,
        }
        if response.status_code >= 500:
            request_logger.error(
                "Heartly request failed %s",
                log_fields,
            )
        elif elapsed_ms >= settings.HEARTLY_SLOW_REQUEST_MILLISECONDS:
            request_logger.warning(
                "Heartly slow request %s",
                log_fields,
            )

        return response


class SessionSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        expired_response = self._enforce_session_limits(request)
        response = (
            expired_response
            if expired_response is not None
            else self.get_response(request)
        )

        if getattr(request, "user", None) is not None:
            if (
                request.user.is_authenticated
                or expired_response is not None
            ):
                no_store(response)

        return add_security_headers(response)

    @staticmethod
    def _enforce_session_limits(request):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None

        now = int(time.time())
        created_at = request.session.get(SESSION_CREATED_KEY)
        activity_at = request.session.get(SESSION_ACTIVITY_KEY)

        if not isinstance(created_at, (int, float)):
            created_at = now
            request.session[SESSION_CREATED_KEY] = now
        if not isinstance(activity_at, (int, float)):
            activity_at = now
            request.session[SESSION_ACTIVITY_KEY] = now

        idle_age = now - int(activity_at)
        absolute_age = now - int(created_at)
        invalid_clock = idle_age < -300 or absolute_age < -300
        expired = (
            invalid_clock
            or idle_age
            > settings.HEARTLY_SESSION_IDLE_TIMEOUT_SECONDS
            or absolute_age
            > settings.HEARTLY_SESSION_ABSOLUTE_TIMEOUT_SECONDS
        )

        if expired:
            next_path = request.get_full_path()
            logout(request)
            login_url = reverse("account_login")
            query = urlencode(
                {
                    "next": next_path,
                    "session": "expired",
                }
            )
            redirect_url = f"{login_url}?{query}"

            if request.method not in {"GET", "HEAD", "OPTIONS"} or wants_json(request):
                return JsonResponse(
                    {
                        "ok": False,
                        "error": "Your session expired. Sign in again.",
                        "login_url": redirect_url,
                    },
                    status=401,
                )
            return redirect(redirect_url)

        if (
            now - int(activity_at)
            >= settings.HEARTLY_SESSION_ACTIVITY_UPDATE_SECONDS
        ):
            request.session[SESSION_ACTIVITY_KEY] = now

        return None


class AbuseRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(
        self,
        request,
        view_func,
        view_args,
        view_kwargs,
    ):
        if not settings.RATELIMIT_ENABLE or request.method != "POST":
            return None

        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and (user.is_staff or user.is_superuser)
        ):
            return None

        match = request.resolver_match
        view_name = match.view_name if match else ""
        group = RATE_LIMIT_VIEW_GROUPS.get(view_name)
        if not group:
            return None

        decision = consume_rate_limit(
            group,
            request_identity(request),
        )
        if decision.allowed:
            return None

        context = {
            "retry_after": decision.retry_after,
        }
        if wants_json(request):
            response = JsonResponse(
                {
                    "ok": False,
                    "error": (
                        "Too many requests. Please wait and try again."
                    ),
                    "retry_after": decision.retry_after,
                },
                status=429,
            )
        else:
            response = render(
                request,
                "account/rate_limited.html",
                context,
                status=429,
            )

        response["Retry-After"] = str(decision.retry_after)
        no_store(response)
        return response
