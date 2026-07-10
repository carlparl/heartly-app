from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from django.http import FileResponse, Http404
from pathlib import Path

from accounts import views as accounts_views
from heartly import pwa_views

def serve_static_file_from_project(request, relative_path, content_type):
    file_path = Path(settings.BASE_DIR) / "static" / relative_path

    if not file_path.exists():
        raise Http404(f"{relative_path} not found")

    return FileResponse(open(file_path, "rb"), content_type=content_type)


def pwa_icon_192(request):
    return serve_static_file_from_project(request, "icons/icon-192.png", "image/png")


def pwa_icon_512(request):
    return serve_static_file_from_project(request, "icons/icon-512.png", "image/png")


def pwa_maskable_192(request):
    return serve_static_file_from_project(request, "icons/maskable-192.png", "image/png")


def pwa_maskable_512(request):
    return serve_static_file_from_project(request, "icons/maskable-512.png", "image/png")


def pwa_registration_js(request):
    return serve_static_file_from_project(request, "js/heartly-pwa.js", "application/javascript")

urlpatterns = [
    path("admin/", admin.site.urls),

    # PWA routes. Keep the service worker at root scope.
    path("manifest.webmanifest", pwa_views.manifest, name="pwa_manifest"),
    path("sw.js", pwa_views.service_worker, name="pwa_service_worker"),
    path("service-worker.js", pwa_views.service_worker, name="pwa_service_worker_compat"),
    path("offline/", pwa_views.offline, name="pwa_offline"),

    path("", include("accounts.urls")),
    path("post-login-redirect/", accounts_views.post_login_redirect, name="post_login_redirect"),
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
