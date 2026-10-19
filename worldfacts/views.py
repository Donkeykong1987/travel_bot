import requests
from urllib.parse import quote
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Place, Favorite, Note

def fetch_wiki_place(query):
    if not query:
        return None
    
    # Kodowanie nazwy do adresu URL (np. spacje na %20)
    encoded_query = quote(query.strip())
    url = f"https://pl.wikipedia.org/api/rest_v1/page/summary/{encoded_query}"
    headers = {'User-Agent': 'WorldfactsApp/1.0'}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('extract'):
                return {
                    'title': data.get('title'),
                    'extract': data.get('extract'),
                    'image_url': data.get('originalimage', {}).get('source', '') if data.get('originalimage') else None,
                    'wiki_id': str(data.get('pageid'))
                }
    except requests.RequestException:
        pass
    return None

def explore_view(request):
    query = request.GET.get('q', '').strip()
    place_obj = None
    is_favorite = False
    notes = []
    searched = False

    if query:
        searched = True
        place_data = fetch_wiki_place(query)
        if place_data:
            place_obj, _ = Place.objects.get_or_create(
                wiki_id=place_data['wiki_id'],
                defaults={
                    'name': place_data['title'],
                    'summary': place_data['extract'],
                    'image_url': place_data['image_url']
                }
            )
            if request.user.is_authenticated:
                is_favorite = Favorite.objects.filter(user=request.user, place=place_obj).exists()
                notes = Note.objects.filter(user=request.user, place=place_obj)

    context = {
        'query': query,
        'searched': searched,
        'place': place_obj,
        'is_favorite': is_favorite,
        'notes': notes
    }
    return render(request, 'places/explore.html', context)

@login_required
def toggle_favorite(request, place_id):
    place = get_object_or_404(Place, id=place_id)
    fav, created = Favorite.objects.get_or_create(user=request.user, place=place)
    if not created:
        fav.delete()
    
    q = request.GET.get('q', '')
    if q:
        return redirect(f"/?q={q}")
    return redirect('explore')

@login_required
def add_note(request, place_id):
    if request.method == 'POST':
        content = request.POST.get('content')
        redirect_q = request.POST.get('redirect_q', '')
        place = get_object_or_404(Place, id=place_id)
        if content:
            Note.objects.create(user=request.user, place=place, content=content)
        if redirect_q:
            return redirect(f"/?q={redirect_q}")
    return redirect('explore')

@login_required
def favorites_list(request):
    favorites = Favorite.objects.filter(user=request.user).select_related('place')
    return render(request, 'places/favorites.html', {'favorites': favorites})