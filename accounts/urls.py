from django.urls import path
from . import views

urlpatterns = [
    path("", views.welcome, name="welcome"),
    path(
        "community-guidelines/",
        views.community_guidelines,
        name="community_guidelines",
    ),
    path(
        "privacy/",
        views.privacy_policy,
        name="privacy_policy",
    ),
    path(
        "terms/",
        views.terms_of_service,
        name="terms_of_service",
    ),

    path("settings/", views.settings_home, name="settings"),
    path("settings/account/", views.settings_account, name="settings_account"),
    path("settings/privacy/", views.settings_privacy, name="settings_privacy"),
    path("settings/notifications/", views.notifications_home, name="notifications_home"),
    path("settings/help/", views.settings_help, name="settings_help"),
    path("settings/about/", views.settings_about, name="settings_about"),

    path("settings/account/send-code/", views.send_email_code, name="send_email_code"),
    path("settings/account/verify-email/", views.verify_email_code, name="verify_email_code"),
    path("settings/account/delete/", views.delete_account, name="delete_account"),
    path("settings/account/export/", views.data_export, name="data_export"),

    path("post-login-redirect/", views.post_login_redirect, name="post_login_redirect"),
]
