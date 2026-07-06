from django.urls import path
from . import views

urlpatterns = [
    path("settings/", views.settings_home, name="settings"),
    path("settings/account/", views.settings_account, name="settings_account"),
    path("settings/privacy/", views.settings_privacy, name="settings_privacy"),
    path("settings/notifications/", views.notifications_home, name="notifications_home"),
    path("settings/help/", views.settings_help, name="settings_help"),
    path("settings/about/", views.settings_about, name="settings_about"),
    path(
    "settings/account/send-code/",
    views.send_email_code,
    name="send_email_code"
),
path(
    "settings/account/verify-email/",
    views.verify_email_code,
    name="verify_email_code"
),
]