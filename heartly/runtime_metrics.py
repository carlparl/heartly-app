import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


logger = logging.getLogger(__name__)
METRIC_NAMES = (
    "requests",
    "responses_4xx",
    "responses_5xx",
    "slow_requests",
    "duration_ms",
)


def hour_start(moment):
    return moment.replace(minute=0, second=0, microsecond=0)


def metric_key(window_start, metric_name):
    stamp = window_start.strftime("%Y%m%d%H")
    return f"heartly:runtime:{stamp}:{metric_name}"


def increment_metric(window_start, metric_name, amount):
    key = metric_key(window_start, metric_name)
    timeout = settings.HEARTLY_RUNTIME_METRIC_TTL_SECONDS
    try:
        created = cache.add(key, int(amount), timeout=timeout)
        if not created:
            cache.incr(key, int(amount))
    except Exception:
        logger.warning(
            "Heartly runtime metric cache unavailable.",
            exc_info=True,
        )


def record_request_metric(status_code, elapsed_ms, *, now=None):
    now = now or timezone.now()
    window_start = hour_start(now)
    status_code = int(status_code)
    elapsed_ms = max(0, int(elapsed_ms))

    increment_metric(window_start, "requests", 1)
    increment_metric(window_start, "duration_ms", elapsed_ms)
    if 400 <= status_code < 500:
        increment_metric(window_start, "responses_4xx", 1)
    if status_code >= 500:
        increment_metric(window_start, "responses_5xx", 1)
    if elapsed_ms >= settings.HEARTLY_SLOW_REQUEST_MILLISECONDS:
        increment_metric(window_start, "slow_requests", 1)


def runtime_snapshot(*, now=None, hours=2):
    now = now or timezone.now()
    current = hour_start(now)
    windows = [
        current - timedelta(hours=offset)
        for offset in range(max(1, int(hours)))
    ]
    totals = {name: 0 for name in METRIC_NAMES}

    try:
        keys = [
            metric_key(window, name)
            for window in windows
            for name in METRIC_NAMES
        ]
        values = cache.get_many(keys)
    except Exception:
        values = {}

    for window in windows:
        for name in METRIC_NAMES:
            value = values.get(metric_key(window, name), 0)
            try:
                totals[name] += max(0, int(value or 0))
            except (TypeError, ValueError):
                continue

    request_count = totals["requests"]
    denominator = request_count or 1
    return {
        "window_hours": len(windows),
        "window_start": windows[-1].isoformat(),
        "window_end": (current + timedelta(hours=1)).isoformat(),
        **totals,
        "error_5xx_percent": round(
            totals["responses_5xx"] * 100 / denominator,
            2,
        ),
        "slow_request_percent": round(
            totals["slow_requests"] * 100 / denominator,
            2,
        ),
        "average_duration_ms": round(
            totals["duration_ms"] / denominator,
            2,
        ),
    }
