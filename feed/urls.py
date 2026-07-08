from django.urls import path

from . import views

app_name = "feed"

urlpatterns = [
    path("", views.feed_home, name="feed_home"),
    path("", views.feed_home, name="home"),

    path("create/", views.create_post, name="create_post"),
    path("post/create/", views.create_post, name="create_post_alt"),

    path("post/<int:post_id>/edit/", views.edit_post, name="edit_post"),
    path("post/<int:post_id>/delete/", views.delete_post, name="delete_post"),

    path("post/<int:post_id>/like/", views.toggle_like, name="toggle_like"),
    path("post/<int:post_id>/like-post/", views.like_post, name="like_post"),

    path("post/<int:post_id>/comment/", views.add_comment, name="add_comment"),
    path("post/<int:post_id>/report/", views.report_post, name="report_post"),
]
