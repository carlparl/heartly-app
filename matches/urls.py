from django.urls import path
from . import views

app_name = "matches"

urlpatterns = [
    path('', views.discover, name='discover'),
    path('like/<int:user_id>/', views.like_user, name='like_user'),
    path('pass/<int:user_id>/', views.pass_user, name='pass_user'),
    path('super/<int:user_id>/', views.super_like, name='super_like'),
    path("", views.discover, name="discover"),
    path('match/<int:user_id>/', views.match_screen, name='match_screen'),
]