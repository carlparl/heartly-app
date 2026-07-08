from django.urls import path

from . import views

app_name = "feed"

urlpatterns = [
    path("", views.feed_home, name="feed_home"),
    path("create/", views.create_post, name="create_post"),

    path("post/<int:post_id>/edit/", views.edit_post, name="edit_post"),
    path("post/<int:post_id>/delete/", views.delete_post, name="delete_post"),
    path("post/<int:post_id>/like/", views.like_post, name="like_post"),
    path("post/<int:post_id>/comment/", views.comment_post, name="comment_post"),
    path("post/<int:post_id>/report/", views.report_post, name="report_post"),

    # Compatibility aliases for older Heartly templates.
    path("post/<int:post_id>/toggle-like/", views.like_post, name="toggle_like"),
    path("post/<int:post_id>/add-comment/", views.comment_post, name="add_comment"),
]
