# Vacations Finder

Szuka wakacji dla rodziny według algorytmu: najpierw tanie loty (Ryanair, z Wrocławia),
potem noclegi blisko morza na booking.com (cena, ocena, udogodnienia).
Szczegóły i decyzje projektowe: [WYMAGANIA.md](WYMAGANIA.md).

## Instalacja (raz)

Wymagany Python 3.11+ (na tym Macu: `python3.13`).

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
```

## Użycie

```bash
.venv/bin/python find_flights.py         # 1. loty        → flights.posredni.json
.venv/bin/python find_lodging.py         # 2. noclegi     → lodging.finalny.json
.venv/bin/python enrich_amenities.py     # 3. (opcja) udogodnienia → dopisuje do lodging.finalny.json
.venv/bin/python rank_lodging.py         # 4. (opcja) ranking wg punktów za udogodnienia → ranking.finalny.json
```

Punktację udogodnień (np. basen, jacuzzi — za co jesteś gotów dopłacić) ustawia się
w sekcji `[scoring.udogodnienia]` w `config.toml`. Uwaga: punkty sumują się za każde
pasujące słowo kluczowe — nakładające się hasła (jacuzzi + hydromasaż) mogą liczyć
tę samą wannę podwójnie; to celowe, żeby dało się "ważyć" ulubione udogodnienia.

## Pliki wynikowe — który jest finalny?

Każdy plik ma na górze pole `file_role`, które mówi to samo co ta tabela:

| Plik | Rola |
|---|---|
| `flights.posredni.json` | 🔧 **pośredni** — półprodukt, wejście dla `find_lodging.py` |
| `lodging.finalny.json` | ✅ **finalny** — kompletny obraz (kryteria, loty z godzinami, noclegi z cenami/ocenami/odległością od plaży/udogodnieniami, sumy lot+nocleg); samoopisujący, nadaje się prosto do analizy przez AI |
| `ranking.finalny.json` | ✅ **finalny** — to samo co wyżej, ale posortowane wg Twojej punktacji udogodnień z `config.toml` |

## Zmiana parametrów

Wszystko w [config.toml](config.toml): lotnisko wylotu, zakres dat i liczba nocy,
skład rodziny, budżet, minimalna ocena, udogodnienia, odległość od plaży,
punktacja udogodnień premium. **Pełny opis każdego klucza, dozwolonych wartości
i tego, który skrypt co czyta: [CONFIG.md](CONFIG.md).**

Listę wszystkich udogodnień występujących w Twoich wynikach (do dobierania
punktacji) wypisuje `python3.13 rank_lodging.py --list-udogodnienia`.

## Przydatne opcje

```bash
.venv/bin/python find_lodging.py --top 10       # sprawdź 10 kierunków zamiast 6
.venv/bin/python enrich_amenities.py --limit 5  # tylko 5 obiektów na kierunek
.venv/bin/python find_lodging.py --headful      # z oknem przeglądarki (debug)
```

`enrich_amenities.py` zapisuje postęp na bieżąco i pomija już uzupełnione obiekty —
przerwany można po prostu odpalić jeszcze raz.

## Dobrze wiedzieć

- Loty: tylko Ryanair (publiczne API, ceny za osobę × 7 osób). Wizz Air nieuwzględniony.
- Noclegi: pierwsza strona wyników bookingu (~25 ofert/kierunek), sortowanie po cenie.
- Booking blokuje zwykłe requesty, stąd headless Chromium (Playwright).
- Dla lotnisk w głębi lądu (Bolonia, Bergamo, Wenecja, Rzym…) nocleg szukany jest
  w najbliższym nadmorskim rejonie (mapa w [common.py](common.py)).
