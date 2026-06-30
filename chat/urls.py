from django.urls import path
from . import views

app_name = "chat"

urlpatterns = [
    path("", views.chat_home, name="chat_home"),
    path("<int:conversation_id>/", views.chat_room, name="chat_room"),
    path("start/<int:user_id>/", views.start_conversation, name="start_conversation"),
]