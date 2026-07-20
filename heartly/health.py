import uuid

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


def health_response(status, http_status):
    response = JsonResponse(
        {
            "service": "heartly",
            "status": status,
        },
        status=http_status,
    )
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


@never_cache
@require_GET
def liveness(request):
    return health_response("ok", 200)


@never_cache
@require_GET
def readiness(request):
    database_ok = False
    cache_ok = False
    cache_key = f"heartly:readiness:{uuid.uuid4().hex}"
    cache_value = uuid.uuid4().hex

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            database_ok = cursor.fetchone() == (1,)
    except Exception:
        database_ok = False

    try:
        cache.set(cache_key, cache_value, timeout=15)
        cache_ok = cache.get(cache_key) == cache_value
    except Exception:
        cache_ok = False
    finally:
        try:
            cache.delete(cache_key)
        except Exception:
            pass

    if database_ok and cache_ok:
        return health_response("ready", 200)
    return health_response("unavailable", 503)
