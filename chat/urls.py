from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("", views.chat_home, name="chat_home"),
    path("start/<int:user_id>/", views.start_chat, name="start_chat"),
    path("<int:thread_id>/", views.chat_room, name="chat_room"),
    path("<int:thread_id>/send/", views.send_message, name="send_message"),
    path("<int:thread_id>/delete/", views.delete_chat, name="delete_chat"),
    path("<int:thread_id>/delete-selected/", views.delete_selected_messages, name="delete_selected_messages"),
    path("<int:thread_id>/block/", views.block_thread_user, name="block_thread_user"),
    path("<int:thread_id>/report/", views.report_thread_user, name="report_thread_user"),
]