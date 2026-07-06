from django.urls import path

from . import views

app_name = "matches"

urlpatterns = [
    path("", views.discover, name="discover"),
    path("discover/", views.discover, name="discover"),
    path("swipe/<int:user_id>/<str:action>/", views.swipe, name="swipe"),
    path("mine/", views.your_matches, name="your_matches"),
]
