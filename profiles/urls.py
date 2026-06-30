from django.urls import path
from . import views

app_name = "profiles"

urlpatterns = [
    path("", views.profile_home, name="profile_home"),
    path("edit/", views.edit_profile, name="edit_profile"),
    path("interests/", views.edit_interests, name="edit_interests"),
]