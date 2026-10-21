from django.db import models
from django.contrib.auth.models import User

class Place(models.Model):
    name = models.CharField(max_length=255)
    wiki_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    summary = models.TextField()
    ai_facts = models.TextField(blank=True, null=True)  # To pole musi tutaj być!
    image_url = models.URLField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites')
    place = models.ForeignKey(Place, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'place')

class Note(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notes')
    place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name='notes')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notatka od {self.user.username} dla {self.place.name}"