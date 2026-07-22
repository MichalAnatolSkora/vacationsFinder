#!/usr/bin/env python3
"""Krok 3: ranking noclegów według punktów za udogodnienia "premium".

Czyta lodging.finalny.json (po enrich_amenities.py) i sekcję [scoring.udogodnienia]
z config.toml. Każdemu obiektowi liczy punkty: słowo kluczowe z configu daje
swoje punkty, jeśli pasuje do początku któregoś słowa w nazwie udogodnienia
(bez rozróżniania wielkości liter) — np. "basen" łapie "Odkryty basen"
i "2 baseny", ale nie "Wanna lub prysznic".

Sortowanie: punkty malejąco, w ramach tych samych punktów cena rosnąco.
Wynik: ranking.finalny.json + czytelne top-listy na stdout.

Uruchamianie: python3.13 rank_lodging.py [--top N]  (bez zależności)
"""

import argparse
import json
import re
import sys
from datetime import datetime

from common import BASE_DIR, LODGING_PATH, load_config

RANKING_PATH = BASE_DIR / "ranking.finalny.json"


def match_amenities(amenities: list[str], keyword: str) -> list[str]:
    """Nazwy udogodnień, w których jakieś słowo zaczyna się od keyword."""
    pattern = re.compile(r"\b" + re.escape(keyword) + r"\w*", re.IGNORECASE)
    return [a for a in amenities if pattern.search(a)]


def score_property(prop: dict, scoring: dict) -> tuple[int, dict]:
    amenities = prop.get("amenities") or []
    matched: dict[str, list[str]] = {}
    score = 0
    for keyword, points in scoring.items():
        hits = match_amenities(amenities, keyword)
        if hits:
            matched[keyword] = hits
            score += points
    return score, matched


def main() -> int:
    parser = argparse.ArgumentParser(description="Ranking noclegów wg punktów za udogodnienia")
    parser.add_argument("--top", type=int, default=15,
                        help="ile pozycji pokazać w rankingu globalnym (domyślnie 15)")
    parser.add_argument("--list-udogodnienia", action="store_true",
                        help="wypisz wszystkie udogodnienia z lodging.finalny.json (z licznikami) i zakończ — "
                             "ściąga do dobierania słów kluczowych w [scoring.udogodnienia]")
    args = parser.parse_args()

    if args.list_udogodnienia:
        if not LODGING_PATH.exists():
            sys.exit(f"Brak {LODGING_PATH.name} — najpierw find_lodging.py i enrich_amenities.py")
        data = json.loads(LODGING_PATH.read_text())
        counts: dict[str, int] = {}
        for search in data["searches"]:
            for prop in search["properties"]:
                for label in prop.get("amenities") or []:
                    counts[label] = counts.get(label, 0) + 1
        for label, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"{n:>4}× {label}")
        print(f"\n{len(counts)} unikalnych udogodnień")
        return 0

    cfg = load_config()
    scoring = cfg.get("scoring", {}).get("udogodnienia")
    if not scoring:
        sys.exit("Brak sekcji [scoring.udogodnienia] w config.toml")
    if not LODGING_PATH.exists():
        sys.exit(f"Brak {LODGING_PATH.name} — najpierw find_lodging.py i enrich_amenities.py")

    data = json.loads(LODGING_PATH.read_text())

    ranked = []
    missing_amenities = 0
    for search in data["searches"]:
        for prop in search["properties"]:
            if not prop.get("amenities"):
                missing_amenities += 1
            score, matched = score_property(prop, scoring)
            entry = {
                "score": score,
                "matched": matched,
                "destination": search["destination"],
                "search_area": search["search_area"],
                "checkin": search["checkin"],
                "checkout": search["checkout"],
                "nights": search["nights"],
                "name": prop["name"],
                "review_score": prop["score"],
                "reviews": prop["reviews"],
                "lodging_total_pln": prop["total_price_pln"],
                "flight_family_total_pln": search["flight_family_total_pln"],
                "flight": search.get("flight"),  # pełne dane lotu (godziny, lotnisko)
                "trip_total_pln": (
                    round(search["flight_family_total_pln"] + prop["total_price_pln"], 2)
                    if prop["total_price_pln"] else None
                ),
                "food_estimate_pln": search.get("food_estimate_pln", 0),
                "trip_total_with_food_pln": (
                    round(search["flight_family_total_pln"] + prop["total_price_pln"]
                          + search.get("food_estimate_pln", 0), 2)
                    if prop["total_price_pln"] else None
                ),
                "beach": prop.get("beach"),
                "url": prop["url"],
            }
            ranked.append(entry)

    ranked.sort(key=lambda e: (-e["score"], e["lodging_total_pln"] or 10**9))

    if missing_amenities:
        print(f"UWAGA: {missing_amenities} obiektów bez danych o udogodnieniach "
              f"(uruchom enrich_amenities.py) — dostały 0 punktów", file=sys.stderr)

    RANKING_PATH.write_text(json.dumps({
        "file_role": "FINALNY — obiekty z lodging.finalny.json posortowane wg "
                     "punktów za udogodnienia z config.toml ([scoring.udogodnienia]).",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "lodging_generated_at": data["generated_at"],
        "note": "Ranking obiektów z lodging.finalny.json wg punktów za udogodnienia. "
                "Sortowanie: punkty malejąco, potem cena za pobyt rosnąco. "
                "matched = które słowo kluczowe złapało które udogodnienia.",
        "scoring": scoring,
        "ranking": ranked,
    }, ensure_ascii=False, indent=2))
    print(f"Zapisano {RANKING_PATH.name} ({len(ranked)} obiektów)\n")

    scored = [e for e in ranked if e["score"] > 0]
    print(f"Punkty zdobyło {len(scored)}/{len(ranked)} obiektów. "
          f"TOP {min(args.top, len(ranked))} (punkty → cena):")
    for e in ranked[:args.top]:
        hits = "; ".join(f"{k}: {', '.join(v)}" for k, v in e["matched"].items()) or "—"
        total = e.get("trip_total_with_food_pln") or e["trip_total_pln"] or "?"
        food = e.get("food_estimate_pln", 0)
        food_part = f" +{food} jedzenie" if food else ""
        print(f"  {e['score']:>2} pkt  {e['lodging_total_pln'] or '?':>6} zł nocleg "
              f"(+{e['flight_family_total_pln']:.0f} lot{food_part} = {total} zł)  "
              f"{e['review_score']} ({e['reviews']} op.)  {e['name'][:44]}")
        print(f"          {e['search_area']}, {e['checkin']} – {e['checkout']}, "
              f"plaża: {e['beach'] or 'brak informacji'}")
        print(f"          {hits}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
