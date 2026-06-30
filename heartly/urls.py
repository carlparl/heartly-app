from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from . import views


urlpatterns = [
    path("admin/", admin.site.urls),

    path("", views.welcome, name="welcome"),
    path("post-login-redirect/", views.post_login_redirect, name="post_login_redirect"),

    path("settings/", views.settings_view, name="settings"),
    path("settings/account/", views.settings_account, name="settings_account"),
    path("settings/privacy/", views.settings_privacy, name="settings_privacy"),
    path("settings/help/", views.settings_help, name="settings_help"),
    path("settings/about/", views.settings_about, name="settings_about"),
    path("settings/delete-account/", views.delete_account, name="delete_account"),
    
    path("notifications/", views.notifications_home, name="notifications_home"),

    path("accounts/", include("allauth.urls")),
    path("profiles/", include("profiles.urls")),
    path("matches/", include("matches.urls")),
    path("chat/", include("chat.urls")),
    path("feed/", include("feed.urls")),
    path("ai/", include("ai_features.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)