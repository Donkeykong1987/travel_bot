from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('worldfacts.urls')),  # Zmiana z 'places.urls' na 'worldfacts.urls'
]