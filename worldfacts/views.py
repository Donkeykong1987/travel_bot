import os
from dotenv import load_dotenv
load_dotenv()
import requests
from urllib.parse import quote
from google import genai
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from .models import Place, Favorite, Note

# Skonfiguruj darmowy klucz API (pobierz z aistudio.google.com)
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def generate_ai_facts(title, text):
    """Generuje fakty z całego internetu i filtruje wyniki wyłącznie do fizycznych miejsc."""
    if not title:
        return ""
    
    models_to_try = ['gemini-3.8-flash', 'gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-2.0-flash']
    
    # Nowy, potężny prompt
    prompt = f"""Jesteś ekspertem ds. geografii i turystyki.
KROK 1: Sprawdź, czy hasło "{title}" (kontekst: "{text}") to fizyczne miejsce na Ziemi, miasto, państwo, zabytek, budynek lub obiekt geograficzny.
Jeśli to NIE JEST miejsce (np. to osoba, postać, pojęcie abstrakcyjne, książka, zespół), zwróć WYŁĄCZNIE słowo: NOT_A_PLACE
KROK 2: Jeśli to JEST miejsce, zignoruj powyższy krótki kontekst z Wikipedii. Przeszukaj CAŁĄ swoją wiedzę (z całego internetu) i wypisz 5 najbardziej fascynujących, tajemniczych lub mało znanych faktów o tym miejscu.
Odpowiedź zwróć WYŁĄCZNIE jako czysty kod HTML (znaczniki <ul> i <li>, bez pogrubień, bez Markdown)."""

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            if response and response.text:
                return response.text.replace('```html', '').replace('```', '').strip()
        except Exception:
            continue
            
    return "<ul><li>Serwery AI są obecnie mocno obciążone. Spróbuj odświeżyć stronę za chwilę.</li></ul>"

def fetch_wiki_place(query):
    """Koryguje błędy w nazwie i pobiera opis z Wikipedii"""
    if not query:
        return None, query
    
    headers = {'User-Agent': 'WorldfactsApp/2.0'}
    
    # 1. Autokorekta: Szukamy najbardziej prawdopodobnej nazwy
    search_url = f"https://pl.wikipedia.org/w/api.php?action=query&list=search&srsearch={quote(query.strip())}&utf8=&format=json&srlimit=1"
    correct_title = query
    try:
        search_resp = requests.get(search_url, headers=headers, timeout=5)
        if search_resp.status_code == 200:
            search_data = search_resp.json()
            if search_data.get('query', {}).get('search'):
                correct_title = search_data['query']['search'][0]['title']
    except requests.RequestException:
        pass

    # 2. Pobieramy pełne dane dla poprawionego tytułu
    url = f"https://pl.wikipedia.org/api/rest_v1/page/summary/{quote(correct_title)}"
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('extract'):
                place_data = {
                    'title': data.get('title'),
                    'extract': data.get('extract'),
                    'image_url': data.get('originalimage', {}).get('source', '') if data.get('originalimage') else None,
                    'wiki_id': str(data.get('pageid'))
                }
                return place_data, correct_title
    except requests.RequestException:
        pass
    return None, correct_title

@login_required(login_url='login')
def explore_view(request):
    query = request.GET.get('q', '').strip()
    place_obj = None
    is_favorite = False
    notes = []
    searched = False
    corrected_name = None
    not_a_place_error = False # Nowa flaga informująca o błędzie walidacji

    if query:
        searched = True
        corrected_name = query
        
        # 1. Sprawdź najpierw w lokalnej bazie
        place_obj = Place.objects.filter(name__iexact=query).first()
        
        # 2. Jeśli nie ma w bazie, pobieramy z Wiki i PROSIMY AI O ZATWIERDZENIE
        if not place_obj:
            place_data, corrected_name = fetch_wiki_place(query)
            if place_data:
                generated_facts = generate_ai_facts(place_data['title'], place_data['extract'])
                
                if "NOT_A_PLACE" in generated_facts:
                    not_a_place_error = True
                    place_obj = None # Odcinamy tworzenie obiektu - to nie jest miejsce!
                else:
                    place_obj, created = Place.objects.get_or_create(
                        wiki_id=place_data['wiki_id'],
                        defaults={
                            'name': place_data['title'],
                            'summary': place_data['extract'],
                            'image_url': place_data['image_url'],
                            'ai_facts': generated_facts if "Serwery" not in generated_facts else ""
                        }
                    )

        # 3. Jeśli obiekt był w bazie, ale AI zawiodło wcześniej (np. błąd 503)
        if place_obj and (not place_obj.ai_facts or "Serwery" in place_obj.ai_facts):
            generated_facts = generate_ai_facts(place_obj.name, place_obj.summary)
            if "NOT_A_PLACE" in generated_facts:
                place_obj.delete() # Usuwamy błędny, stary rekord
                not_a_place_error = True
                place_obj = None
            else:
                if "Serwery" not in generated_facts:
                    place_obj.ai_facts = generated_facts
                    place_obj.save()
                else:
                    place_obj.ai_facts = generated_facts

        # 4. Obsługa ulubionych i notatek
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
        'not_a_place_error': not_a_place_error
    }
    return render(request, 'worldfacts/explore.html', context)

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
        place = get_object_or_404(Place, id=place_id)
        # Weryfikacja: Notatka zostanie zapisana TYLKO jeśli miejsce jest w Ulubionych
        if Favorite.objects.filter(user=request.user, place=place).exists():
            content = request.POST.get('content')
            redirect_q = request.POST.get('redirect_q', '')
            if content:
                Note.objects.create(user=request.user, place=place, content=content)
            if redirect_q:
                return redirect(f"/?q={redirect_q}")
    return redirect('explore')

@login_required
def favorites_list(request):
    favorites = Favorite.objects.filter(user=request.user).select_related('place')
    return render(request, 'worldfacts/favorites.html', {'favorites': favorites})

def register_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('explore')
    else:
        form = UserCreationForm()
    return render(request, 'worldfacts/register.html', {'form': form})