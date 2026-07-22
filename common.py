"""Wspólne elementy skryptów Vacations Finder (config, ścieżki, stałe)."""

import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    sys.exit("Potrzebny Python 3.11+ (moduł tomllib). Uruchom np.: python3.13 <skrypt>")

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.toml"
# Rola pliku jest częścią nazwy: .posredni = półprodukt, .finalny = wynik końcowy.
FLIGHTS_PATH = BASE_DIR / "flights.posredni.json"
LODGING_PATH = BASE_DIR / "lodging.finalny.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

COUNTRY_CODES = {
    "Włochy": "IT",
    "Hiszpania": "ES",
    "Malta": "MT",
    "Grecja": "GR",
    "Chorwacja": "HR",
}

# Lotniska w głębi lądu → nadmorski rejon, w którym szukamy noclegu
# (założenie z wymagań: wynajem auta, plaża do ~20 km od lokum).
AIRPORT_COASTAL_AREA = {
    "BLQ": "Rimini",          # Bolonia — wybrzeże Adriatyku ~1h autem
    "BGY": "Liguria",         # Bergamo — najbliższe morze ~2h autem
    "TSF": "Lido di Jesolo",  # Wenecja-Treviso
    "VCE": "Lido di Jesolo",  # Wenecja
    "CIA": "Lido di Ostia",   # Rzym-Ciampino
    "FCO": "Lido di Ostia",   # Rzym-Fiumicino
    "GRO": "Costa Brava",     # Barcelona-Girona
    "SVQ": "Costa de la Luz", # Sewilla — wybrzeże ~1h autem
    "BDS": "Ostuni",          # Brindisi — plaże Apulii ~40 min autem
    "SUF": "Tropea",          # Lamezia — perła Kalabrii ~50 min autem
    "PMO": "Cefalù",          # Palermo — rodzinne plaże Sycylii ~1h autem
}

# Kody filtrów booking.com (nflt) dla udogodnień z config.toml.
# Zweryfikowane na żywej stronie 2026-07-20.
BOOKING_AMENITY_CODES = {
    "klimatyzacja": "roomfacility=11",
    "kuchnia": "roomfacility=999",   # "Kuchnia/aneks kuchenny"
    "wifi": "hotelfacility=107",
    # Wyżywienie (booking: filtr "Posiłki"; kilka wpisów naraz działa jak "albo")
    "sniadanie": "mealplan=1",
    "sniadanie i kolacja": "mealplan=9",
    "pelne wyzywienie": "mealplan=3",
    "all inclusive": "mealplan=4",
    # Basen
    "basen": "hotelfacility=433",
    "prywatny basen": "roomfacility=93",
    # Typ obiektu (booking: ht_id; kilka wpisów naraz działa jak "albo")
    "willa": "ht_id=213",
    "dom wakacyjny": "ht_id=220",
    "hotel": "ht_id=204",
    "apartament": "ht_id=201",
}


def load_config() -> dict:
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def pax_count(cfg: dict) -> int:
    return cfg["osoby"]["dorosli"] + len(cfg["osoby"]["dzieci"])
