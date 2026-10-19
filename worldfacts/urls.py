from django.urls import path
from . import views

urlpatterns = [
    path('', views.explore_view, name='explore'),
    path('favorite/<int:place_id>/', views.toggle_favorite, name='toggle_favorite'),
    path('note/add/<int:place_id>/', views.add_note, name='add_note'),
    path('favorites/', views.favorites_list, name='favorites_list'),
]