from django.urls import path
from . import views

urlpatterns = [
    path("", views.welcome, name="welcome"),
    path("post-login-redirect/", views.post_login_redirect, name="post_login_redirect"),
    path("settings/", views.settings_view, name="settings"),

]