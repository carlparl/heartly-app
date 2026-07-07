from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts import views as accounts_views

urlpatterns = [
    path("admin/", admin.site.urls),
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