from django.urls import path
from . import views

app_name = "chat"

urlpatterns = [
    path("", views.chat_home, name="chat_home"),
    path("start/<int:user_id>/", views.start_chat, name="start_chat"),

    path("<int:thread_id>/", views.chat_room, name="chat_room"),
    path("<int:thread_id>/send/", views.send_message, name="send_message"),

    path("<int:thread_id>/call/start/<str:call_type>/", views.start_call, name="start_call"),
    path("call/<int:call_id>/", views.call_room, name="call_room"),
    path("call/<int:call_id>/accept/", views.accept_call, name="accept_call"),
    path("call/<int:call_id>/decline/", views.decline_call, name="decline_call"),
    path("call/<int:call_id>/end/", views.end_call, name="end_call"),

    path("<int:thread_id>/clear/", views.clear_chat_for_me, name="clear_chat_for_me"),
    path("<int:thread_id>/delete/", views.delete_chat_for_me, name="delete_chat_for_me"),
    path("<int:thread_id>/delete-hard/", views.delete_chat, name="delete_chat"),

    path("<int:thread_id>/messages/delete/", views.delete_selected_messages, name="delete_selected_messages"),
    path("messages/delete-for-me/", views.delete_selected_messages_for_me, name="delete_selected_messages_for_me"),
    path("messages/delete-for-everyone/", views.delete_selected_messages_for_everyone, name="delete_selected_messages_for_everyone"),

    path("message/<int:message_id>/attachment/", views.open_message_attachment, name="open_message_attachment"),

    path("<int:thread_id>/block/", views.block_thread_user, name="block_thread_user"),
    path("<int:thread_id>/report/", views.report_thread_user, name="report_thread_user"),
]
