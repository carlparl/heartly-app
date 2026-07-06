from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.notifications_home, name="notifications_home"),
    path("<int:notification_id>/open/", views.open_notification, name="open_notification"),
    path("<int:notification_id>/clear/", views.clear_notification, name="clear_notification"),

    path("mark-read/", views.mark_notifications_read, name="mark_notifications_read"),
    path("mark-all-read/", views.mark_notifications_read, name="mark_all_read"),

    path("clear-all/", views.clear_all_notifications, name="clear_all_notifications"),
    path("clear-all-old/", views.clear_all_notifications, name="clear_all"),
]