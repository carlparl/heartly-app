from django.urls import path

from . import views

app_name = "profiles"

urlpatterns = [
    path("", views.profile_home, name="profile_home"),
    path("edit/", views.edit_profile, name="edit_profile"),
    path(
        "identity/repair/",
        views.repair_identity,
        name="repair_identity",
    ),
    path("interests/", views.edit_interests, name="edit_interests"),

    path("details/", views.profile_details, name="profile_details"),
    path("activity/", views.profile_activity, name="profile_activity"),
    path("media/", views.profile_media, name="profile_media"),

    path("user/<int:user_id>/", views.public_profile, name="public_profile"),
    path("user/<int:user_id>/report/", views.report_profile, name="report_profile"),
    path("user/<int:user_id>/block/", views.block_user, name="block_user"),
    path("user/<int:user_id>/unblock/", views.unblock_user, name="unblock_user"),

    path("visibility/toggle/", views.toggle_profile_visibility, name="toggle_profile_visibility"),
    path("online-status/toggle/", views.toggle_online_status, name="toggle_online_status"),
    path("message-requests/toggle/", views.toggle_message_requests, name="toggle_message_requests"),
    path("safety-filters/toggle/", views.toggle_safety_filters, name="toggle_safety_filters"),
]
