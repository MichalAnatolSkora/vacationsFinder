#!/usr/bin/env python3
"""Krok 2: sprawdzanie noclegów na booking.com dla kierunków z flights.posredni.json.

Czyta wyniki find_flights.py (flights.posredni.json), dla najtańszych kierunków otwiera
wyszukiwanie booking.com w headless przeglądarce (booking blokuje zwykłe
requesty), zbiera oferty z pierwszej strony wyników i zapisuje lodging.finalny.json.

Filtry wpięte w zapytanie: daty pod konkretny lot, skład rodziny, max cena/noc
z budżetu, minimalna ocena, udogodnienia (kody z common.BOOKING_AMENITY_CODES),
sortowanie po cenie rosnąco.

Uruchamianie: .venv/bin/python find_lodging.py [--top N]
Wymaga: pip install playwright && playwright install chromium
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime

from common import (
    AIRPORT_COASTAL_AREA,
    BOOKING_AMENITY_CODES,
    COUNTRY_URL_CODES,
    FLIGHTS_PATH,
    LODGING_PATH,
    USER_AGENT,
    load_config,
)

PAGE_TIMEOUT_MS = 45_000

EXTRACT_CARDS_JS = """
() => Array.from(document.querySelectorAll('[data-testid="property-card"]')).map(card => {
  const text = sel => { const el = card.querySelector(sel); return el ? el.innerText : null; };
  const link = card.querySelector('a[data-testid="title-link"], a[data-testid="property-card-desktop-single-image"]');
  return {
    name: text('[data-testid="title"]'),
    review_block: text('[data-testid="review-score"]'),
    price_block: text('[data-testid="price-and-discounted-price"]'),
    distance: text('[data-testid="distance"]'),
    url: link ? link.href : null,
    card_text: card.innerText,
  };
})
"""


def build_booking_url(cfg: dict, area: str, checkin: str, checkout: str,
                      nights: int, max_per_night: int) -> str:
    nocleg = cfg["nocleg"]

    params = [
        ("ss", area),
        ("checkin", checkin),
        ("checkout", checkout),
        ("group_adults", cfg["osoby"]["dorosli"]),
        ("no_rooms", 1),
        ("group_children", len(cfg["osoby"]["dzieci"])),
        *[("age", wiek) for wiek in cfg["osoby"]["dzieci"]],
        ("selected_currency", "PLN"),
        ("order", "price"),  # najtańsze najpierw
    ]

    nflt = [
        f"review_score={int(float(nocleg['ocena_min']) * 10)}",
        f"price=PLN-min-{max_per_night}-1",
    ]
    for amenity in nocleg["udogodnienia"]:
        code = BOOKING_AMENITY_CODES.get(amenity.lower())
        if code:
            nflt.append(code)
        else:
            print(f"  UWAGA: brak kodu filtra booking dla udogodnienia "
                  f"'{amenity}' — zweryfikuj ręcznie", file=sys.stderr)
    params.append(("nflt", ";".join(nflt)))

    return "https://www.booking.com/searchresults.pl.html?" + urllib.parse.urlencode(params)


def parse_price_pln(text: str | None) -> int | None:
    """'1 714 zł' / 'od 12 500 zł' → 1714 / 12500."""
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def parse_review(block: str | None) -> tuple[float | None, int | None]:
    """Blok opinii ('Znakomity\\n9,2\\n214 opinii') → (9.2, 214)."""
    if not block:
        return None, None
    score = None
    m = re.search(r"\b(\d[.,]\d)\b", block)
    if m:
        score = float(m.group(1).replace(",", "."))
    reviews = None
    m = re.search(r"([\d\s]+)\s*opini", block)
    if m:
        reviews = int(re.sub(r"\D", "", m.group(1)))
    return score, reviews


def beach_note(card_text: str) -> str | None:
    """Wyciąga z karty informacje o plaży (np. 'Przy plaży', '350 m od plaży')."""
    hits = re.findall(
        r"Przy plaży|Nad plażą|[\d.,]+\s*(?:m|km)\s+od plaży", card_text
    )
    return "; ".join(dict.fromkeys(hits)) or None


def parse_card(raw: dict, cfg: dict, search: dict) -> dict | None:
    if not raw.get("name"):
        return None
    nights = search["nights"]
    score, reviews = parse_review(raw.get("review_block"))
    total = parse_price_pln(raw.get("price_block"))
    url = raw.get("url")
    if url:
        url = url.split("?")[0]  # bazowy link; kontekst dat/osób dokłada scrape_destination

    prop = {
        "name": raw["name"].strip(),
        "score": score,
        "reviews": reviews,
        "total_price_pln": total,
        "price_per_night_pln": round(total / nights) if total else None,
        "distance_from_center": raw.get("distance"),
        "beach": beach_note(raw.get("card_text", "")),
        "url": url,
    }

    # Filtr bezpieczeństwa — booking zwykle to respektuje w nflt, ale bywa,
    # że karta "promowana" przecieka mimo filtrów.
    if total is not None and total > search["lodging_budget_pln"]:
        return None
    min_score = float(cfg["nocleg"]["ocena_min"])
    if score is not None and score < min_score:
        return None
    return prop


def scrape_destination(page, cfg: dict, search: dict) -> list[dict]:
    page.goto(search["booking_url"], timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
    # Baner cookies: odrzucamy zbędne, żeby nie zasłaniał wyników.
    try:
        page.click("#onetrust-reject-all-handler", timeout=4_000)
    except Exception:
        pass
    page.wait_for_selector('[data-testid="property-card"]', timeout=PAGE_TIMEOUT_MS)
    raw_cards = page.evaluate(EXTRACT_CARDS_JS)

    # Booking dokleja pod wynikami karty "może Ci się spodobać" spoza filtrów —
    # nagłówek ("Rimini: znaleziono 3 obiekty") mówi, ile kart jest prawdziwych.
    h1 = page.evaluate("(document.querySelector('h1') || {}).innerText || ''")
    m = re.search(r"znaleziono\s+([\d\s]+)\s+obiek", h1)
    if m:
        raw_cards = raw_cards[: int(re.sub(r"\D", "", m.group(1)))]

    props = [parse_card(r, cfg, search) for r in raw_cards]
    props = [p for p in props if p]
    # Link do obiektu z gotowym kontekstem: daty pobytu + skład rodziny,
    # żeby po kliknięciu booking od razu pokazał właściwą cenę i dostępność.
    for p in props:
        if p["url"]:
            p["url"] = p["url"] + "?" + urllib.parse.urlencode([
                ("checkin", search["checkin"]),
                ("checkout", search["checkout"]),
                ("group_adults", cfg["osoby"]["dorosli"]),
                ("no_rooms", 1),
                ("group_children", len(cfg["osoby"]["dzieci"])),
                *[("age", wiek) for wiek in cfg["osoby"]["dzieci"]],
                ("selected_currency", "PLN"),
            ])
    return props


MIN_LODGING_BUDGET_PLN = 3000  # poniżej tego nie ma czego szukać dla 7 osób


def build_manual_searches(cfg: dict, args) -> list[dict]:
    """Tryb ręczny: lot już kupiony, szukamy tylko noclegów w zadanych rejonach."""
    from datetime import date
    checkin, checkout = args.checkin, args.checkout
    nights = (date.fromisoformat(checkout) - date.fromisoformat(checkin)).days
    lodging_budget, food_est = lodging_budget_for(cfg, args.flight_cost_pln, nights)
    searches = []
    for area in [a.strip() for a in args.areas.split(",") if a.strip()]:
        searches.append({
            "destination": f"lot własny ({args.country})",
            "country": args.country,
            "airport": None,
            "search_area": area,
            "checkin": checkin,
            "checkout": checkout,
            "nights": nights,
            "flight_family_total_pln": args.flight_cost_pln,
            "flight": {
                "airport": "-", "airport_name": "lot własny (kupiony poza wyszukiwarką)",
                "city": "-", "outbound": f"{checkin}T00:00:00", "inbound": f"{checkout}T00:00:00",
                "nights": nights, "price_per_person": None, "currency": "PLN",
                "family_total": args.flight_cost_pln, "baggage_est_pln": 0,
                "family_total_with_bags": args.flight_cost_pln,
            },
            "lodging_budget_pln": lodging_budget,
            "food_estimate_pln": food_est,
            "max_price_per_night_pln": lodging_budget // nights,
            "booking_url": build_booking_url(cfg, area, checkin, checkout, nights,
                                             lodging_budget // nights),
        })
    return searches


def lodging_budget_for(cfg: dict, flight_total: float, nights: int) -> tuple[int, int]:
    """(budżet na nocleg, szacunek jedzenia). Z sekcji [budzet] liczymy:
    całkowity - lot - jedzenie; bez niej stały [nocleg].budzet_max_pln."""
    budzet = cfg.get("budzet")
    if not budzet:
        return int(cfg["nocleg"]["budzet_max_pln"]), 0
    food = int(budzet.get("jedzenie_dzien_pln", 0)) * nights
    return int(budzet["calkowity_pln"] - flight_total - food), food


def build_searches(cfg: dict, flights: dict, top: int) -> list[dict]:
    searches = []
    for dest in flights["destinations"][:top]:
        best = dest["options"][0]
        checkin, checkout = best["outbound"][:10], best["inbound"][:10]
        areas = AIRPORT_COASTAL_AREA.get(dest["airport"], dest["city"])
        if isinstance(areas, str):
            areas = [areas]
        # Koszt lotu z bagażem (jeśli policzony) — to on obciąża budżet całkowity.
        flight_total = best.get("family_total_with_bags", best["family_total"])
        lodging_budget, food_est = lodging_budget_for(cfg, flight_total, best["nights"])
        if lodging_budget < MIN_LODGING_BUDGET_PLN:
            print(f"  POMIJAM {dest['city']}: po locie ({best['family_total']:.0f} zł) "
                  f"i jedzeniu ({food_est} zł) na nocleg zostaje tylko {lodging_budget} zł",
                  file=sys.stderr)
            continue
        for area in areas:
            search = {
                "destination": f"{dest['city']} ({dest['country']})",
                "country": dest["country"],
                "airport": dest["airport"],
                "search_area": area,
                "checkin": checkin,
                "checkout": checkout,
                "nights": best["nights"],
                "flight_family_total_pln": flight_total,
                # Pełne dane lotu — plik ma opisywać całość, bez zaglądania do flights.posredni.json.
                "flight": best,
                "lodging_budget_pln": lodging_budget,
                "food_estimate_pln": food_est,
                "max_price_per_night_pln": lodging_budget // best["nights"],
                "booking_url": build_booking_url(cfg, area, checkin, checkout, best["nights"],
                                                 lodging_budget // best["nights"]),
            }
            if area != dest["city"]:
                search["coast_note"] = (
                    f"Nocleg szukany w nadmorskim rejonie: {area} "
                    f"(dojazd wynajętym autem z lotniska {dest['city']})."
                )
            searches.append(search)
    return searches


def main() -> int:
    parser = argparse.ArgumentParser(description="Sprawdza noclegi booking.com dla kierunków z flights.posredni.json")
    parser.add_argument("--top", type=int, default=6,
                        help="ile najtańszych kierunków z flights.posredni.json sprawdzić (domyślnie 6)")
    parser.add_argument("--headful", action="store_true",
                        help="pokaż okno przeglądarki (debug)")
    # Tryb ręczny — gdy lot jest już kupiony: własne daty i rejony zamiast flights.posredni.json.
    parser.add_argument("--checkin", help="tryb ręczny: data zameldowania (RRRR-MM-DD)")
    parser.add_argument("--checkout", help="tryb ręczny: data wymeldowania (RRRR-MM-DD)")
    parser.add_argument("--areas", help="tryb ręczny: rejony po przecinku, np. 'Rimini,Riccione'")
    parser.add_argument("--country", default="Włochy",
                        help="tryb ręczny: kraj rejonów (walidacja wyników; domyślnie Włochy)")
    parser.add_argument("--flight-cost-pln", type=float, default=0.0,
                        help="tryb ręczny: koszt kupionego lotu (do budżetu całkowitego i sum)")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        sys.exit("Brak Playwrighta. Zainstaluj:\n"
                 "  .venv/bin/pip install playwright && .venv/bin/playwright install chromium\n"
                 "i uruchamiaj: .venv/bin/python find_lodging.py")

    cfg = load_config()
    manual_mode = bool(args.checkin or args.checkout or args.areas)
    if manual_mode:
        if not (args.checkin and args.checkout and args.areas):
            sys.exit("Tryb ręczny wymaga naraz: --checkin, --checkout i --areas")
        flights = {"generated_at": None}
        searches = build_manual_searches(cfg, args)
    else:
        if not FLIGHTS_PATH.exists():
            sys.exit(f"Brak {FLIGHTS_PATH.name} — najpierw uruchom find_flights.py")
        flights = json.loads(FLIGHTS_PATH.read_text())
        searches = build_searches(cfg, flights, args.top)
    errors: list[str] = []

    print(f"Sprawdzam booking.com dla {len(searches)} kierunków "
          f"(budżet {cfg['nocleg']['budzet_max_pln']} zł, "
          f"ocena {cfg['nocleg']['ocena_min']}+, "
          f"udogodnienia: {', '.join(cfg['nocleg']['udogodnienia'])})")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headful)
        # Normalny UA jest konieczny — z domyślnym "HeadlessChrome" booking
        # serwuje pustą stronę wyszukiwania bez wyników.
        context = browser.new_context(
            locale="pl-PL",
            user_agent=USER_AGENT,
            viewport={"width": 1400, "height": 900},
        )
        page = context.new_page()
        seen_by_dest: dict[str, set] = {}

        def run_search(search: dict) -> bool:
            """Jedno wyszukiwanie z deduplikacją; True gdy się udało."""
            try:
                props = scrape_destination(page, cfg, search)
            except Exception as e:
                msg = f"{search['destination']} → {search['search_area']}: {type(e).__name__}: {str(e)[:160]}"
                print(f"    UWAGA: {msg}", file=sys.stderr)
                search["properties"] = []
                search["_error"] = msg
                return False
            # Ten sam obiekt może wpaść z kilku sąsiednich rejonów — bierzemy 1. wystąpienie.
            seen = seen_by_dest.setdefault(search["destination"], set())
            expected_cc = COUNTRY_URL_CODES.get(search.get("country", ""), None)
            search["properties"] = []
            for p in props:
                base = (p["url"] or "").split("?")[0]
                if base and base in seen:
                    continue
                # ss bywa niejednoznaczne — odrzucamy obiekty z innego kraju niż kierunek.
                m = re.search(r"/hotel/([a-z]{2})/", base)
                if expected_cc and m and m.group(1) != expected_cc:
                    print(f"    pomijam obiekt z innego kraju ({m.group(1)}): {p['name'][:40]}",
                          file=sys.stderr)
                    continue
                seen.add(base)
                search["properties"].append(p)
            search.pop("_error", None)
            return True

        failed = []
        for search in searches:
            print(f"  {search['destination']} → {search['search_area']} "
                  f"({search['checkin']} – {search['checkout']})...", flush=True)
            if not run_search(search):
                failed.append(search)
            time.sleep(2)  # nie prowokujemy limitów bookingu przy dziesiątkach zapytań

        # Druga szansa dla timeoutów — zwykle chwilowe dławienie, nie twarda blokada.
        if failed:
            print(f"  Ponawiam {len(failed)} nieudanych wyszukiwań...", flush=True)
            time.sleep(15)
            for search in failed:
                print(f"  [retry] {search['destination']} → {search['search_area']}...", flush=True)
                if not run_search(search):
                    errors.append(search.pop("_error", f"{search['destination']}: retry nieudany"))
                time.sleep(4)

        for search in searches:
            search["properties_found"] = len(search["properties"])
            cheapest = next((p for p in search["properties"] if p["total_price_pln"]), None)
            if cheapest:
                search["cheapest_total_trip_pln"] = round(
                    search["flight_family_total_pln"] + cheapest["total_price_pln"], 2
                )
        browser.close()

    results = {
        "file_role": "FINALNY — kompletny obraz: kryteria, loty, noclegi "
                     "(po enrich_amenities.py także udogodnienia). Wersja "
                     "posortowana wg preferencji udogodnień: ranking.finalny.json.",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "flights_generated_at": flights["generated_at"],
        "note": "Oferty z 1. strony wyników booking (sortowanie: cena rosnąco), "
                "max ~25 obiektów na kierunek. Ceny łączne za cały pobyt dla 7 osób. "
                "cheapest_total_trip_pln = lot (rodzina) + najtańszy nocleg.",
        "criteria": {
            "budget_total_pln": cfg["nocleg"]["budzet_max_pln"],
            "min_score": cfg["nocleg"]["ocena_min"],
            "amenities": cfg["nocleg"]["udogodnienia"],
            "max_km_from_beach": cfg["nocleg"]["max_km_od_plazy"],
        },
        "errors": errors,
        "searches": searches,
    }
    LODGING_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nZapisano {LODGING_PATH.name}")

    print("\nPodsumowanie (lot dla 7 os. + najtańszy pasujący nocleg):")
    for s in sorted(searches, key=lambda x: x.get("cheapest_total_trip_pln", 9e9)):
        if s.get("cheapest_total_trip_pln"):
            print(f"  {s['cheapest_total_trip_pln']:>9.0f} zł  {s['destination']:<28} "
                  f"nocleg w: {s['search_area']:<16} ofert: {s['properties_found']}")
        else:
            print(f"  {'—':>9}     {s['destination']:<28} "
                  f"nocleg w: {s['search_area']:<16} ofert: {s['properties_found']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
