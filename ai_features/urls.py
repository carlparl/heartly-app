from django.urls import path
from . import views

app_name = "ai_features"

urlpatterns = [
    path("", views.ai_coach_page, name="ai_coach_page"),
]