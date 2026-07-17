from django.urls import path

from . import views

app_name = "feed"

urlpatterns = [
    path("", views.feed_home, name="feed_home"),
    path("create/", views.create_post, name="create_post"),

    path("stories/create/", views.create_story, name="create_story"),
    path("stories/<int:story_id>/", views.story_detail, name="story_detail"),
    path("stories/<int:story_id>/react/", views.react_story, name="react_story"),
    path("stories/<int:story_id>/delete/", views.delete_story, name="delete_story"),

    path("post/<int:post_id>/edit/", views.edit_post, name="edit_post"),
    path("post/<int:post_id>/delete/", views.delete_post, name="delete_post"),

    path("post/<int:post_id>/like/", views.like_post, name="like_post"),
    path("post/<int:post_id>/react/", views.like_post, name="react_post"),
    path("post/<int:post_id>/save/", views.save_post, name="save_post"),

    path("post/<int:post_id>/comment/", views.comment_post, name="comment_post"),
    path("post/<int:post_id>/report/", views.report_post, name="report_post"),

    path("comment/<int:comment_id>/reply/", views.reply_comment, name="reply_comment"),
    path("comment/<int:comment_id>/react/", views.react_comment, name="react_comment"),

    # Compatibility aliases
    path("post/<int:post_id>/toggle-like/", views.like_post, name="toggle_like"),
    path("post/<int:post_id>/add-comment/", views.comment_post, name="add_comment"),
]
