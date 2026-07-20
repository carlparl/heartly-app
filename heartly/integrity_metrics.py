from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


EVENT_LIMITED = "limited"


def _hour_start(moment):
    return moment.replace(minute=0, second=0, microsecond=0)


def _key(window_start, group):
    stamp = window_start.strftime("%Y%m%d%H")
    return f"heartly:integrity:{stamp}:{group}:{EVENT_LIMITED}"


def record_rate_limit_event(group, *, now=None):
    if group not in settings.HEARTLY_RATE_LIMITS:
        return
    now = now or timezone.now()
    key = _key(_hour_start(now), group)
    try:
        created = cache.add(
            key,
            1,
            timeout=settings.HEARTLY_RUNTIME_METRIC_TTL_SECONDS,
        )
        if not created:
            cache.incr(key)
    except Exception:
        # Rate limiting remains authoritative. Telemetry is best effort.
        return


def integrity_snapshot(*, now=None, hours=2):
    now = now or timezone.now()
    current = _hour_start(now)
    windows = [
        current - timedelta(hours=offset)
        for offset in range(max(1, int(hours)))
    ]
    groups = sorted(settings.HEARTLY_RATE_LIMITS)
    keys = [_key(window, group) for window in windows for group in groups]
    try:
        values = cache.get_many(keys)
    except Exception:
        values = {}

    by_group = {}
    for group in groups:
        total = 0
        for window in windows:
            try:
                total += max(0, int(values.get(_key(window, group), 0) or 0))
            except (TypeError, ValueError):
                continue
        by_group[group] = total

    return {
        "window_hours": len(windows),
        "window_start": windows[-1].isoformat(),
        "window_end": (current + timedelta(hours=1)).isoformat(),
        "limited_requests": sum(by_group.values()),
        "by_group": by_group,
        "contains_request_identity": False,
        "contains_request_content": False,
    }
