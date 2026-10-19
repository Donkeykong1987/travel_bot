from django.contrib import admin
from django.urls import path, include  # Pamiętaj o zaimportowaniu 'include'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('places.urls')),  # Podpięcie adresów aplikacji places pod adres główny
]