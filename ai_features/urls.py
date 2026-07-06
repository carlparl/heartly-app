from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = "ai_features"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="ai_features:ai_coach", permanent=False), name="ai_home"),
    path("coach/", views.ai_coach_page, name="ai_coach"),
    path("send/", views.ai_coach_send, name="ai_coach_send"),
    path("end/", views.ai_coach_end_chat, name="ai_coach_end_chat"),
]