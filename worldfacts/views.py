import os
import requests
from urllib.parse import urlencode
from difflib import SequenceMatcher
from dotenv import load_dotenv
from google import genai
import time
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login

from .models import Place, Favorite, Note

load_dotenv()

# Skonfiguruj darmowy klucz API (pobierz z aistudio.google.com)
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def generate_ai_facts(title, text):
    """Generuje fakty z AI z systemem inteligentnego ponawiania (retry) w przypadku przeciążenia."""
    if not title:
        return ""
    
    prompt = f"""Jesteś ekspertem ds. geografii i turystyki.
KROK 1: Sprawdź, czy hasło "{title}" (kontekst: "{text}") to fizyczne miejsce na Ziemi, miasto, państwo, zabytek, budynek lub obiekt geograficzny.
Jeśli to NIE JEST miejsce, zwróć WYŁĄCZNIE słowo: NOT_A_PLACE
KROK 2: Jeśli to JEST miejsce, zignoruj powyższy krótki kontekst z Wikipedii. Przeszukaj CAŁĄ swoją wiedzę i wypisz 5 najbardziej fascynujących, tajemniczych lub mało znanych faktów o tym miejscu.
Odpowiedź zwróć WYŁĄCZNIE jako czysty kod HTML (znaczniki <ul> i <li>, bez pogrubień, bez Markdown)."""

    model_name = 'gemini-3.8-flash'
    max_retries = 3  # Maksymalna liczba prób
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            if response and response.text:
                return response.text.replace('```html', '').replace('```', '').strip()
        except Exception as e:
            error_msg = str(e)
            print(f"--- Próba {attempt + 1}/{max_retries} nieudana ({model_name}): {error_msg} ---")
            
            # Jeśli to błąd 503, czekamy 2.5 sekundy i próbujemy ponownie
            if "503" in error_msg:
                time.sleep(2.5)
            else:
                # Inny błąd (np. autoryzacji) - nie ma sensu czekać, przerywamy
                break
            
    return "<ul><li>Serwery AI Google są w tej chwili mocno przeciążone. Odczekaj dłuższą chwilę i odśwież stronę.</li></ul>"

def fetch_wiki_place(query):
    """Pobiera dane z Wikipedii z inteligentnym dopasowaniem oraz bezpiecznym nagłówkiem."""
    url = "https://pl.wikipedia.org/w/api.php"
    
    # DODANO: Nagłówek User-Agent chroniący przed zablokowaniem przez Wikipedię
    headers = {
        'User-Agent': 'WorldfactsApp/1.0 (contact@example.com)'
    }
    
    search_params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": query,
        "utf8": 1,
        "srlimit": 5
    }
    
    try:
        response = requests.get(url, params=search_params, headers=headers)
        data = response.json()
        search_results = data.get("query", {}).get("search", [])
        
        if not search_results:
            return None, None
            
        best_match = None
        highest_ratio = 0.0
        
        first_result_title = search_results[0]["title"]
        
        for result in search_results:
            title = result["title"]
            ratio = SequenceMatcher(None, query.lower(), title.lower()).ratio()
            
            if query.lower() in title.lower():
                ratio += 0.3
                
            if ratio > highest_ratio:
                highest_ratio = ratio
                best_match = title

        if highest_ratio < 0.3 or not best_match:
            best_match = first_result_title

        details_params = {
            "action": "query",
            "format": "json",
            "prop": "extracts|pageimages",
            "exintro": 1,
            "explaintext": 1,
            "titles": best_match,
            "pithumbsize": 800
        }
        
        det_resp = requests.get(url, params=details_params, headers=headers)
        det_data = det_resp.json()
        pages = det_data.get("query", {}).get("pages", {})
        
        for page_id, page_info in pages.items():
            if page_id == "-1":
                continue
                
            result_data = {
                'wiki_id': str(page_id),
                'title': page_info.get('title'),
                'extract': page_info.get('extract', 'Brak opisu.'),
                'image_url': page_info.get('thumbnail', {}).get('source', '')
            }
            
            return result_data, best_match
            
    except Exception as e:
        print(f"\n--- BŁĄD WYSZUKIWANIA WIKIPEDII ---")
        print(f"Szczegóły: {e}")
        print("-----------------------------------\n")
        return None, None
        
    return None, None

@login_required(login_url='login')
def explore_view(request):
    """Główny widok wyszukiwarki (bez blokowania na API AI)."""
    query = request.GET.get('q', '').strip()
    place_obj = None
    is_favorite = False
    notes = []
    searched = False
    corrected_name = None

    if query:
        searched = True
        corrected_name = query
        
        place_obj = Place.objects.filter(name__iexact=query).first()
        
        if not place_obj:
            place_data, corrected_name = fetch_wiki_place(query)
            if place_data:
                place_obj, created = Place.objects.get_or_create(
                    wiki_id=place_data['wiki_id'],
                    defaults={
                        'name': place_data['title'],
                        'summary': place_data['extract'],
                        'image_url': place_data['image_url'],
                        'ai_facts': ''
                    }
                )
        
        if place_obj and request.user.is_authenticated:
            is_favorite = Favorite.objects.filter(user=request.user, place=place_obj).exists()
            notes = Note.objects.filter(user=request.user, place=place_obj)

    recent_places = Place.objects.all().order_by('-created_at')[:5]

    context = {
        'query': query,
        'searched': searched,
        'place': place_obj,
        'is_favorite': is_favorite,
        'notes': notes,
        'recent_places': recent_places,
        'original_query': query,
        'corrected_name': corrected_name,
    }
    return render(request, 'worldfacts/explore.html', context)

@login_required
def get_ai_facts_api(request, place_id):
    """Endpoint AJAX pobierający ciekawostki w tle."""
    try:
        place = Place.objects.get(id=place_id)
    except Place.DoesNotExist:
        return JsonResponse({'status': 'error'})

    if place.ai_facts and "Serwery" not in place.ai_facts:
        return JsonResponse({'status': 'success', 'facts': place.ai_facts})

    generated_facts = generate_ai_facts(place.name, place.summary)

    if "NOT_A_PLACE" in generated_facts:
        place.delete()
        return JsonResponse({'status': 'not_a_place'})
    elif "Serwery" in generated_facts:
        return JsonResponse({'status': 'error', 'facts': generated_facts})
    else:
        place.ai_facts = generated_facts
        place.save()
        return JsonResponse({'status': 'success', 'facts': generated_facts})

@login_required(login_url='login')
def toggle_favorite(request, place_id):
    """Dodaje lub usuwa miejsce z ulubionych i bezpiecznie przekierowuje."""
    place = get_object_or_404(Place, id=place_id)
    favorite = Favorite.objects.filter(user=request.user, place=place).first()
    
    query = request.GET.get('q', '')
    source = request.GET.get('source', '') # Sprawdzamy z jakiej podstrony kliknięto
    
    if favorite:
        favorite.delete()
        Note.objects.filter(user=request.user, place=place).delete()
    else:
        Favorite.objects.create(user=request.user, place=place)
        
    # Jeśli kliknięto usuń w zakładce Ulubione, zostajemy w Ulubionych
    if source == 'favorites':
        return redirect('favorites_list')
        
    if query:
        redirect_url = f"{reverse('explore')}?{urlencode({'q': query})}"
        return redirect(redirect_url)
    return redirect('explore')

@login_required(login_url='login')
def add_note(request, place_id):
    """Dodaje notatkę weryfikując czy obiekt jest w ulubionych i wraca do widoku Ulubionych."""
    if request.method == 'POST':
        place = get_object_or_404(Place, id=place_id)
        
        if Favorite.objects.filter(user=request.user, place=place).exists():
            content = request.POST.get('content', '').strip()
            if content:
                Note.objects.create(user=request.user, place=place, content=content)
                
    # Po dodaniu notatki zawsze wracamy do zakładki Favorites
    return redirect('favorites_list')

@login_required
def favorites_list(request):
    """Wyświetla listę ulubionych wraz z przypisanymi notatkami."""
    # Pobieramy ulubione miejsca
    favorites = Favorite.objects.filter(user=request.user).select_related('place').order_by('-created_at')
    
    # Doczepiamy notatki do każdego ulubionego miejsca, aby łatwo je wyświetlić w HTML
    for fav in favorites:
        fav.place_notes = Note.objects.filter(user=request.user, place=fav.place).order_by('-created_at')
        
    return render(request, 'worldfacts/favorites.html', {'favorites': favorites})

def register_view(request):
    """Obsługuje rejestrację nowych użytkowników."""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('explore')
    else:
        form = UserCreationForm()
    return render(request, 'worldfacts/register.html', {'form': form})

@login_required(login_url='login')
def delete_note(request, note_id):
    """Usuwa pojedynczą notatkę (tylko jeśli należy do zalogowanego użytkownika)."""
    if request.method == 'POST':
        # Zabezpieczenie: szukamy notatki należącej TYLKO do tego konkretnego usera
        note = get_object_or_404(Note, id=note_id, user=request.user)
        note.delete()
    return redirect('favorites_list')