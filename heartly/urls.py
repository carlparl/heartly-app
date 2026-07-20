from pathlib import Path

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import FileResponse, Http404
from django.urls import include, path

from accounts import views as accounts_views
from heartly import health
from heartly import pwa_views


def serve_static_file_from_project(request, relative_path, content_type):
    """Serve PWA-critical files from stable root URLs.

    These routes keep PWA installation working even if a deployment's
    collected static filenames are hashed or an old static cache is present.
    """
    file_path = Path(settings.BASE_DIR) / "static" / relative_path

    if not file_path.exists():
        raise Http404(f"{relative_path} not found")

    response = FileResponse(file_path.open("rb"), content_type=content_type)
    response["Cache-Control"] = "public, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def pwa_icon_192(request):
    return serve_static_file_from_project(request, "icons/icon-192.png", "image/png")


def pwa_icon_512(request):
    return serve_static_file_from_project(request, "icons/icon-512.png", "image/png")


def pwa_maskable_192(request):
    return serve_static_file_from_project(request, "icons/maskable-192.png", "image/png")


def pwa_maskable_512(request):
    return serve_static_file_from_project(request, "icons/maskable-512.png", "image/png")


def pwa_registration_js(request):
    return serve_static_file_from_project(
        request,
        "js/heartly-pwa.js",
        "application/javascript; charset=utf-8",
    )


urlpatterns = [
    path("admin/", admin.site.urls),

    # Aggregate probes expose no database, cache, user, or version details.
    path("health/live/", health.liveness, name="health_liveness"),
    path("health/ready/", health.readiness, name="health_readiness"),

    # Root-scoped PWA files.
    path("manifest.webmanifest", pwa_views.manifest, name="pwa_manifest"),
    path("sw.js", pwa_views.service_worker, name="pwa_service_worker"),
    path(
        "service-worker.js",
        pwa_views.service_worker,
        name="pwa_service_worker_compat",
    ),
    path("offline/", pwa_views.offline, name="pwa_offline"),

    # Stable PWA assets. These do not depend on WhiteNoise hashed filenames.
    path("pwa/heartly-pwa.js", pwa_registration_js, name="pwa_registration_js"),
    path("pwa/icon-192.png", pwa_icon_192, name="pwa_icon_192"),
    path("pwa/icon-512.png", pwa_icon_512, name="pwa_icon_512"),
    path("pwa/maskable-192.png", pwa_maskable_192, name="pwa_maskable_192"),
    path("pwa/maskable-512.png", pwa_maskable_512, name="pwa_maskable_512"),

    path("", include("accounts.urls")),
    path(
        "post-login-redirect/",
        accounts_views.post_login_redirect,
        name="post_login_redirect",
    ),
    path("settings/", accounts_views.settings_view, name="settings"),
    path("accounts/", include("allauth.urls")),
    path("profiles/", include("profiles.urls")),
    path("matches/", include("matches.urls")),
    path("chat/", include("chat.urls")),
    path("ai/", include("ai_features.urls")),
    path("feed/", include("feed.urls")),
    path("notifications/", include("notifications.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
