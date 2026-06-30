from django.urls import path
from . import views

app_name = "feed"

urlpatterns = [
    path("", views.feed_home, name="feed_home"),
    path("create/", views.create_post, name="create_post"),
    path("<int:post_id>/like/", views.like_post, name="like_post"),
    path("<int:post_id>/comment/", views.add_comment, name="add_comment"),
    path("<int:post_id>/edit/", views.edit_post, name="edit_post"),
    path("<int:post_id>/delete/", views.delete_post, name="delete_post"),
]