#!/usr/bin/env python3
"""Krok 2b (opcjonalny): dopisuje do lodging.finalny.json udogodnienia każdego obiektu.

Czyta lodging.finalny.json (wynik find_lodging.py), dla każdego obiektu otwiera jego
stronę na booking.com i wyciąga pełną listę udogodnień ("Najpopularniejsze
udogodnienia" + wszystkie grupy z sekcji udogodnień). Wynik zapisuje z powrotem
do lodging.finalny.json — do każdego obiektu dochodzi pole "amenities" (płaska,
odduplikowana lista po polsku), a do korzenia "amenities_enriched_at".

Dzięki temu kolejne skrypty mogą customowo punktować i sortować obiekty
po dowolnym udogodnieniu (np. basen, parking, pralka, widok na morze).

Uruchamianie: .venv/bin/python enrich_amenities.py [--limit N]
"""

import argparse
import json
import sys
from datetime import datetime

from common import LODGING_PATH, USER_AGENT

PAGE_TIMEOUT_MS = 30_000

EXTRACT_AMENITIES_JS = """
() => {
  const texts = [];
  document.querySelectorAll('[data-testid="property-most-popular-facilities-wrapper"] li')
    .forEach(li => texts.push(li.innerText));
  document.querySelectorAll('[data-testid="property-facilities-block-container"] li')
    .forEach(li => texts.push(li.innerText));
  return texts;
}
"""


def clean_amenities(raw: list[str]) -> list[str]:
    """Płaska, odduplikowana lista; z wielolinijkowych pozycji bierzemy 1. linię.

    Booking dopisuje w kolejnych liniach m.in. "Dodatkowa opłata" — to istotna
    informacja (np. płatny klub dla dzieci), więc zachowujemy ją w nawiasie.
    """
    seen = {}
    for t in raw:
        lines = [l.strip() for l in t.split("\n") if l.strip()]
        if not lines:
            continue
        name = lines[0]
        if any("opłat" in l.lower() for l in lines[1:]):
            name += " (dodatkowa opłata)"
        if name not in seen:
            seen[name] = None
    return list(seen)


def fetch_amenities(page, url: str) -> list[str]:
    page.goto(url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
    # Pełna sekcja udogodnień dogrywa się JS-em po załadowaniu i renderuje
    # dopiero po podscrollowaniu strony — bez tego selektor nigdy nie wstaje.
    page.wait_for_timeout(2_000)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
    page.wait_for_selector(
        '[data-testid="property-facilities-block-container"] li',
        timeout=PAGE_TIMEOUT_MS,
    )
    return clean_amenities(page.evaluate(EXTRACT_AMENITIES_JS))


def main() -> int:
    parser = argparse.ArgumentParser(description="Dopisuje udogodnienia obiektów do lodging.finalny.json")
    parser.add_argument("--limit", type=int, default=None,
                        help="max obiektów na kierunek (domyślnie: wszystkie)")
    parser.add_argument("--headful", action="store_true",
                        help="pokaż okno przeglądarki (debug)")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        sys.exit("Brak Playwrighta — patrz requirements.txt")

    if not LODGING_PATH.exists():
        sys.exit(f"Brak {LODGING_PATH.name} — najpierw uruchom find_lodging.py")

    data = json.loads(LODGING_PATH.read_text())
    todo = []
    for search in data["searches"]:
        props = search["properties"][: args.limit] if args.limit else search["properties"]
        # Braki i wcześniejsze błędy (amenities == None) próbujemy ponownie.
        todo.extend(p for p in props if p.get("url") and not p.get("amenities"))

    print(f"Do uzupełnienia: {len(todo)} obiektów "
          f"(już wzbogacone pomijam; --limit {args.limit or 'brak'})")

    errors = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headful)
        context = browser.new_context(
            locale="pl-PL",
            user_agent=USER_AGENT,  # z "HeadlessChrome" booking nie oddaje treści
            viewport={"width": 1400, "height": 900},
        )
        # Bez obrazków/fontów strony ładują się szybciej. CSS musi zostać —
        # bez arkuszy booking nie dorenderowuje sekcji udogodnień.
        context.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ("image", "font", "media")
            else route.continue_(),
        )
        page = context.new_page()

        for i, prop in enumerate(todo, 1):
            try:
                prop["amenities"] = fetch_amenities(page, prop["url"])
                prop.pop("amenities_error", None)
                status = f"{len(prop['amenities'])} udogodnień"
            except Exception as e:
                prop["amenities"] = None
                prop["amenities_error"] = f"{type(e).__name__}: {str(e)[:120]}"
                errors += 1
                status = f"BŁĄD ({type(e).__name__})"
            print(f"  [{i}/{len(todo)}] {prop['name'][:50]}: {status}", flush=True)

            # Zapis po każdym obiekcie — przerwany run nie traci postępu,
            # a ponowne uruchomienie dociąga tylko braki.
            data["amenities_enriched_at"] = datetime.now().isoformat(timespec="seconds")
            LODGING_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))

        browser.close()

    print(f"\nZapisano {LODGING_PATH.name} ({len(todo) - errors} OK, {errors} błędów)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
