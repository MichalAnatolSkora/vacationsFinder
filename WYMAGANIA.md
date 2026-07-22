# Vacations Finder — wymagania

Automat do szukania wakacji. Docelowo skrypt w Pythonie, który realizuje poniższy algorytm i zwraca wyniki do sprawdzenia.

## Algorytm szukania

### Krok 1: Tanie loty

Najpierw szukamy tanich lotów. Kraje docelowe (preferowane):

- Włochy
- Hiszpania
- Malta
- Grecja
- Chorwacja

Kryterium: cena lotu (im taniej, tym lepiej). Kierunek z tanim lotem wyznacza, gdzie dalej szukamy noclegu.

### Krok 2: Nocleg (głównie booking.com)

Dla wybranego kierunku szukamy lokum według parametrów:

| Parametr | Opis |
|---|---|
| Cena maksymalna | zadana kwota za pobyt / za noc (do ustalenia) |
| Ocena minimalna | zadana minimalna ocena obiektu (np. 8.0+) |
| Udogodnienia | lista wymaganych udogodnień (np. klimatyzacja, WiFi, kuchnia — do ustalenia) |
| Lokalizacja | blisko wybrzeża — tak, żeby dało się jeździć na plażę |

## Parametry wejściowe skryptu

Wszystkie parametry są konfigurowalne w pliku [`config.toml`](config.toml) — skrypt czyta go na starcie (Python: wbudowany moduł `tomllib`, bez zależności).

Wartości domyślne:

| Parametr | Domyślna wartość |
|---|---|
| Lotnisko wylotu | Wrocław (WRO) |
| Zakres dat | 17.08.2026 – 30.08.2026 |
| Długość pobytu | 7–9 nocy |
| Osoby | 7: 3 dorosłych + 4 dzieci (4, 7, 7, 8 lat) |
| Budżet na nocleg | 12 000 zł za cały pobyt |
| Minimalna ocena noclegu | 8.0 (do potwierdzenia) |
| Udogodnienia | kuchnia, klimatyzacja |
| Max odległość od plaży | 20 km (planowany wynajem auta na miejscu) |
| Budżet na loty | bez limitu — szukamy najtańszych |

## Architektura — odizolowane skrypty

Pipeline: `config.toml` → `find_flights.py` → `flights.posredni.json` *(pośredni)* → `find_lodging.py` (+`enrich_amenities.py`) → `lodging.finalny.json` *(finalny)* → `rank_lodging.py` → `ranking.finalny.json` *(finalny, posortowany)* → przegląd (Claude/AI). Role plików opisuje pole `file_role` w każdym z nich oraz tabela w [README.md](README.md).

| Plik | Rola |
|---|---|
| [`common.py`](common.py) | wspólne: config, ścieżki, mapy (kody krajów, rejony nadmorskie, kody filtrów booking) |
| [`find_flights.py`](find_flights.py) | najtańsze loty (API Ryanaira, bez zależności) → `flights.posredni.json` |
| [`find_lodging.py`](find_lodging.py) | czyta `flights.posredni.json`, sprawdza booking.com headless przeglądarką (Playwright) → `lodging.finalny.json` |
| [`enrich_amenities.py`](enrich_amenities.py) | (opcjonalny krok 2b) dopisuje do obiektów w `lodging.finalny.json` pełne listy udogodnień ze stron obiektów — baza pod customowy scoring/sortowanie |
| [`rank_lodging.py`](rank_lodging.py) | (krok 3) ranking obiektów wg punktów za udogodnienia z `[scoring.udogodnienia]` w configu (punkty malejąco, potem cena rosnąco) → `ranking.finalny.json` |

Uruchamianie:

```bash
# jednorazowo (Python 3.11+):
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium

# szukanie:
.venv/bin/python find_flights.py
.venv/bin/python find_lodging.py --top 6      # ile najtańszych kierunków sprawdzić
.venv/bin/python enrich_amenities.py          # opcjonalnie: udogodnienia obiektów
```

`enrich_amenities.py` zapisuje postęp po każdym obiekcie i pomija już wzbogacone — przerwany run można po prostu uruchomić ponownie.

Co robi `find_lodging.py`: dla każdego kierunku buduje wyszukiwanie booking z wpiętymi filtrami (daty pod konkretny lot, 3 dorosłych + 4 dzieci z wiekami, max cena/noc z budżetu, min ocena, klimatyzacja + kuchnia, sortowanie po cenie), zbiera oferty z 1. strony wyników (max ~25/kierunek) i zapisuje: nazwę, ocenę, liczbę opinii, cenę za pobyt, odległość od plaży, link. Dla lotnisk w głębi lądu (Bolonia, Bergamo, Wenecja…) szuka w najbliższym nadmorskim rejonie. Booking blokuje zwykłe requesty (challenge JS) — stąd Playwright; konieczny też normalny User-Agent, bo na „HeadlessChrome" booking oddaje pustą stronę.

Ograniczenia v1: loty tylko Ryanair (z WRO to główny przewoźnik na te kierunki; Wizz Air nieuwzględniony); noclegi tylko 1. strona wyników; odległość od plaży tylko gdy booking pokazuje ją na karcie.

## Plan realizacji

1. ✅ Spisanie wymagań w tym pliku.
2. ✅ `find_flights.py` — loty.
3. ✅ `find_lodging.py` — noclegi z booking.com.
4. ✅ Wyniki w `flights.posredni.json` / `lodging.finalny.json`.
5. Claude sprawdza i ocenia `lodging.finalny.json` — filtruje, rankuje, wyłapuje okazje i podejrzane oferty, proponuje najlepsze kombinacje lot + nocleg.

## Format outputu skryptu (propozycja)

Skrypt zwraca JSON z listą kandydatów, każdy zawiera:

- kierunek (kraj, miasto, lotnisko)
- lot: cena, daty, przewoźnik, link
- nocleg: nazwa, cena łączna, ocena, odległość od plaży, udogodnienia, link
- suma kosztów (lot + nocleg)
