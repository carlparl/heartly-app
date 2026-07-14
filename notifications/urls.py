from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.notifications_home, name="notifications_home"),
    path(
        "broadcast/create/",
        views.create_broadcast,
        name="create_broadcast",
    ),
    path(
        "broadcast/<int:batch_id>/",
        views.broadcast_detail,
        name="broadcast_detail",
    ),
    path("snapshot/", views.notification_snapshot_view, name="snapshot"),
    path("unread-count/", views.unread_count, name="unread_count"),
    path("push/config/", views.push_config, name="push_config"),
    path("push/subscribe/", views.push_subscribe, name="push_subscribe"),
    path("push/unsubscribe/", views.push_unsubscribe, name="push_unsubscribe"),
    path(
        "<int:notification_id>/open/",
        views.open_notification,
        name="open_notification",
    ),
    path(
        "<int:notification_id>/clear/",
        views.clear_notification,
        name="clear_notification",
    ),
    path(
        "mark-read/",
        views.mark_notifications_read,
        name="mark_notifications_read",
    ),
    path(
        "mark-all-read/",
        views.mark_notifications_read,
        name="mark_all_read",
    ),
    path(
        "clear-all/",
        views.clear_all_notifications,
        name="clear_all_notifications",
    ),
    path(
        "clear-all-old/",
        views.clear_all_notifications,
        name="clear_all",
    ),
]
