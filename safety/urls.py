from django.urls import path

from . import views


app_name = "safety"


urlpatterns = [
    path("block/user/<int:user_id>/", views.block_user, name="block_user"),
    path("unblock/user/<int:user_id>/", views.unblock_user, name="unblock_user"),

    path("report/user/<int:user_id>/", views.report_user, name="report_user"),
    path("report/post/<int:post_id>/", views.report_post, name="report_post"),
    path("report/comment/<int:comment_id>/", views.report_comment, name="report_comment"),
]