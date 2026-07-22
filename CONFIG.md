# CONFIG.md — jak tworzyć i zmieniać config.toml

Wszystkie parametry wyszukiwania siedzą w jednym pliku: [config.toml](config.toml).
Skrypty czytają go na starcie — zmiana wartości nie wymaga dotykania kodu.
Format pliku to [TOML](https://toml.io/en/) (klucz = wartość, sekcje w `[nawiasach]`).

## Które skrypty czytają które sekcje

| Sekcja | find_flights.py | find_lodging.py | enrich_amenities.py | rank_lodging.py |
|---|:-:|:-:|:-:|:-:|
| `[wylot]` | ✓ | | | |
| `[daty]` | ✓ | ✓ (daty pod konkretny lot) | | |
| `[osoby]` | ✓ (cena × liczba osób) | ✓ (skład w zapytaniu booking) | | |
| `[kierunki]` | ✓ | | | |
| `[nocleg]` | | ✓ | | |
| `[loty]` | (zarezerwowane, na razie nieużywane) | | | |
| `[scoring.udogodnienia]` | | | | ✓ |

`enrich_amenities.py` nie czyta configu — pracuje wprost na `lodging.finalny.json`.

## Sekcje i dozwolone wartości

### `[wylot]`

| Klucz | Typ | Opis |
|---|---|---|
| `lotnisko` | string | Kod IATA lotniska wylotu, np. `"WRO"`, `"WAW"`, `"KRK"`, `"POZ"`. Musi być lotniskiem obsługiwanym przez Ryanaira. |

### `[daty]`

| Klucz | Typ | Opis |
|---|---|---|
| `od` | data (`RRRR-MM-DD`, bez cudzysłowów) | Najwcześniejszy dzień wylotu. |
| `do` | data | Najpóźniejszy dzień powrotu. |
| `min_nocy`, `max_nocy` | liczba całkowita | Widełki długości pobytu. Muszą się mieścić w oknie dat. |

### `[osoby]`

| Klucz | Typ | Opis |
|---|---|---|
| `dorosli` | liczba całkowita | Liczba dorosłych. |
| `dzieci` | lista liczb | Wiek każdego dziecka, np. `[4, 7, 7, 8]`. Pusta lista `[]` = bez dzieci. Wiek trafia do zapytania booking (wpływa na dopłaty i dostępność). |

### `[kierunki]`

| Klucz | Typ | Opis |
|---|---|---|
| `kraje` | lista stringów | Kraje do przeszukania. **Dozwolone wartości** (mapa `COUNTRY_CODES` w [common.py](common.py)): `"Włochy"`, `"Hiszpania"`, `"Malta"`, `"Grecja"`, `"Chorwacja"`. Inny kraj → ostrzeżenie i pominięcie. Żeby dodać nowy, dopisz go do `COUNTRY_CODES` (kod ISO, np. `"Portugalia": "PT"`). |

### `[budzet]` (opcjonalna — budżet całkowity)

| Klucz | Typ | Opis |
|---|---|---|
| `calkowity_pln` | liczba | Budżet **na całość**: lot + nocleg + jedzenie. Gdy sekcja istnieje, budżet na nocleg jest liczony osobno dla każdego kierunku: `calkowity - lot rodziny - jedzenie`. Kierunki, gdzie na nocleg zostaje < 3000 zł, są pomijane (z komunikatem). |
| `jedzenie_dzien_pln` | liczba | Szacunek wydatków na jedzenie dla całej rodziny za dzień (przy własnym wyżywieniu). Mnożony przez liczbę nocy. |

Usunięcie/zakomentowanie sekcji przywraca stary tryb: stały `[nocleg].budzet_max_pln`.

### `[nocleg]`

| Klucz | Typ | Opis |
|---|---|---|
| `budzet_max_pln` | liczba | Budżet na nocleg **za cały pobyt** (nie za noc). Skrypt przelicza na max cenę/noc dla dat danego lotu. |
| `ocena_min` | liczba (np. `8.0`) | Minimalna ocena obiektu na booking (skala 1–10). Sensowne wartości: 6.0–9.0, booking filtruje progami co 1.0. |
| `udogodnienia` | lista stringów | Udogodnienia **wymagane** — wpinane jako filtr już w zapytaniu booking. **Dozwolone wartości** = klucze mapy `BOOKING_AMENITY_CODES` w [common.py](common.py): obecnie `"kuchnia"`, `"klimatyzacja"`, `"wifi"`, `"basen"`, `"prywatny basen"`; wyżywienie: `"sniadanie"`, `"sniadanie i kolacja"`, `"pelne wyzywienie"`, `"all inclusive"`; typ obiektu: `"willa"`, `"dom wakacyjny"`, `"hotel"`, `"apartament"` (kilka wpisów wyżywienia lub typu naraz = "albo-albo"). Nieznana wartość → ostrzeżenie i pominięcie filtra (reszta działa dalej). Jak dodać nową — patrz niżej. Uwaga: `"kuchnia"` + wyżywienie naraz mocno zawęża wyniki (hotele z posiłkami rzadko mają kuchnie). |
| `max_km_od_plazy` | liczba | Deklarowany zasięg do plaży. Uwaga: obecnie **informacyjne** — trafia do `lodging.finalny.json`, ale nie odfiltrowuje wyników (odległość od plaży znamy tylko, gdy booking pokaże ją na karcie). |

### `[loty]`

| Klucz | Typ | Opis |
|---|---|---|
| `budzet_max_pln` | liczba | Zarezerwowane na przyszły limit ceny lotów; `0` = bez limitu. Obecnie nieużywane — szukamy po prostu najtańszych. |

### `[scoring.udogodnienia]` — punkty za udogodnienia premium

Każdy wpis to `słowo-klucz = punkty`. Używa go tylko `rank_lodging.py`:
obiekt dostaje punkty za każde słowo-klucz, które pasuje do któregoś z jego
udogodnień; ranking sortuje po punktach malejąco, potem po cenie rosnąco.

```toml
[scoring.udogodnienia]
basen = 5
jacuzzi = 5
"hydromasaż" = 5      # klucze z polskimi znakami lub spacją muszą być w cudzysłowie
sauna = 2
"prywatna plaża" = 3
```

Zasady:

- **Wartości to dowolne słowa** — nie ma zamkniętej listy. Dopasowanie jest po
  **początku słowa**, bez rozróżniania wielkości liter: `basen` łapie „Odkryty
  basen", „2 baseny", „Basen dla dzieci"; nie łapie „Wanna lub prysznic".
- Punkty są **dowolnymi liczbami** — większa liczba = ważniejsze udogodnienie.
- Punkty **sumują się za każde słowo-klucz osobno** — nakładające się hasła
  (`jacuzzi` + `hydromasaż`) mogą policzyć tę samą wannę podwójnie. To celowe
  (ważenie), ale miej to na uwadze przy interpretacji wyników.
- Skąd brać słowa? Wypisz wszystkie udogodnienia występujące w Twoich wynikach:

  ```bash
  python3.13 rank_lodging.py --list-udogodnienia
  ```

  (291 unikalnych etykiet w obecnych danych; na górze najczęstsze, np.
  „Klimatyzacja", „Kuchnia", „Balkon", „Widok na morze", „Prywatna plaża").

## Jak dodać nowe udogodnienie do filtrów booking (`[nocleg] udogodnienia`)

Wymagane udogodnienia filtrują wyniki już po stronie booking — potrzebują kodu
filtra `nflt` (np. klimatyzacja = `roomfacility=11`). Kody siedzą w mapie
`BOOKING_AMENITY_CODES` w [common.py](common.py). Żeby dodać np. basen:

1. Otwórz w przeglądarce dowolne wyszukiwanie booking.com i zaznacz filtr „Basen".
2. Spójrz na URL — w parametrze `nflt` pojawi się kod, np. `hotelfacility=433`.
3. Dopisz do `BOOKING_AMENITY_CODES`: `"basen": "hotelfacility=433"`.
4. Dodaj `"basen"` do listy `udogodnienia` w config.toml.

Kody bywają różne per typ filtra (`roomfacility=` — udogodnienia w pokoju,
`hotelfacility=` — w obiekcie) i mogą się z czasem zmieniać — stąd trzymamy
tylko zweryfikowane.

## Rzeczy, których w configu (celowo) nie ma

- **Liczba sprawdzanych kierunków** — flaga `--top` w `find_lodging.py` (domyślnie 6).
- **Długość rankingu** — flaga `--top` w `rank_lodging.py` (domyślnie 15).
- **Lotniska w głębi lądu → rejon nadmorski** — mapa `AIRPORT_COASTAL_AREA` w [common.py](common.py); edytuj ją, żeby zmienić np. Bolonia→Rimini na Bolonia→Riccione.
