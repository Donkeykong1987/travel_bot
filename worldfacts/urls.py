from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.explore_view, name='explore'),
    path('favorite/<int:place_id>/', views.toggle_favorite, name='toggle_favorite'),
    path('note/<int:place_id>/', views.add_note, name='add_note'),
    path('note/delete/<int:note_id>/', views.delete_note, name='delete_note'),
    path('favorites/', views.favorites_list, name='favorites_list'),
    
    # Ścieżka API obsługująca sztuczną inteligencję w tle
    path('api/facts/<int:place_id>/', views.get_ai_facts_api, name='get_ai_facts_api'),
    
    # Rejestracja i logowanie
    path('register/', views.register_view, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='worldfacts/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='explore'), name='logout'),
]