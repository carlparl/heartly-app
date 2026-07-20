import hashlib
import logging
import time
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int


def request_identity(request):
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        raw_identity = f"user:{user.pk}"
    else:
        remote_address = request.META.get("REMOTE_ADDR", "unknown")
        if settings.HEARTLY_TRUST_X_FORWARDED_FOR:
            forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
            if forwarded:
                remote_address = forwarded.split(",", 1)[0].strip()
        raw_identity = f"ip:{remote_address or 'unknown'}"

    return hashlib.sha256(
        raw_identity.encode("utf-8")
    ).hexdigest()


def user_identity(user_id):
    return hashlib.sha256(
        f"user:{int(user_id)}".encode("utf-8")
    ).hexdigest()


def consume_user_rate_limit(group, user_id):
    return consume_rate_limit(
        group,
        user_identity(user_id),
    )


def consume_rate_limit(group, identity, *, now=None):
    if not settings.RATELIMIT_ENABLE:
        return RateLimitDecision(True, 0, 0, 0)

    rule = settings.HEARTLY_RATE_LIMITS.get(group)
    if not rule:
        return RateLimitDecision(True, 0, 0, 0)

    limit = max(1, int(rule.get("limit", 1)))
    window = max(1, int(rule.get("window", 60)))
    timestamp = float(time.time() if now is None else now)
    window_number = int(timestamp // window)
    retry_after = max(
        1,
        window - int(timestamp % window),
    )
    cache_key = (
        f"heartly:rate:{group}:{identity}:{window_number}"
    )

    try:
        created = cache.add(
            cache_key,
            1,
            timeout=window + 5,
        )
        count = 1 if created else cache.incr(cache_key)
    except Exception:
        logger.exception(
            "Heartly rate-limit cache unavailable for group %s",
            group,
        )
        return RateLimitDecision(True, limit, limit, 0)

    if not isinstance(count, int):
        logger.error(
            "Heartly rate-limit cache returned no counter for group %s",
            group,
        )
        return RateLimitDecision(True, limit, limit, 0)

    return RateLimitDecision(
        allowed=count <= limit,
        limit=limit,
        remaining=max(0, limit - count),
        retry_after=retry_after,
    )
