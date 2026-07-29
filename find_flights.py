#!/usr/bin/env python3
"""Krok 1: najtańsze loty w obie strony z zadanego lotniska do krajów z listy.

Źródło: publiczne API wyszukiwarki tanich lotów Ryanaira (bez klucza).
Wejście: config.toml. Wyjście: flights.posredni.json + podsumowanie na stdout.
Uruchamianie: python3.13 find_flights.py  (albo .venv/bin/python find_flights.py)
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from common import COUNTRY_CODES, FLIGHTS_PATH, USER_AGENT, load_config, pax_count

FARFND_URL = "https://services-api.ryanair.com/farfnd/v4/roundTripFares"

# Ile najlepszych kombinacji dat trzymamy per kierunek.
OPTIONS_PER_DESTINATION = 3


def http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_country_fares(cfg: dict, country_code: str) -> list[dict]:
    """Najtańsze pary lotów tam/powrót do jednego kraju."""
    date_from: date = cfg["daty"]["od"]
    date_to: date = cfg["daty"]["do"]
    min_nights = cfg["daty"]["min_nocy"]
    max_nights = cfg["daty"]["max_nocy"]

    params = {
        "departureAirportIataCode": cfg["wylot"]["lotnisko"],
        "outboundDepartureDateFrom": date_from.isoformat(),
        "outboundDepartureDateTo": (date_to - timedelta(days=min_nights)).isoformat(),
        "inboundDepartureDateFrom": (date_from + timedelta(days=min_nights)).isoformat(),
        "inboundDepartureDateTo": date_to.isoformat(),
        "durationFrom": min_nights,
        "durationTo": max_nights,
        "arrivalCountryCode": country_code.lower(),  # API wymaga małych liter
        "market": "pl-pl",
        "currency": "PLN",
        "adultPaxCount": 1,
        "searchMode": "ALL",
        "outboundDepartureTimeFrom": "00:00",
        "outboundDepartureTimeTo": "23:59",
        "inboundDepartureTimeFrom": "00:00",
        "inboundDepartureTimeTo": "23:59",
    }
    url = FARFND_URL + "?" + urllib.parse.urlencode(params)
    data = http_get_json(url)
    return data.get("fares", [])


def baggage_estimate(cfg: dict) -> int:
    """Szacunek za bagaż rejestrowany: sztuki × 2 kierunki × stawka."""
    loty = cfg.get("loty", {})
    return int(loty.get("bagaz_rejestrowany_szt", 0)) \
        * 2 * int(loty.get("bagaz_pln_szt_kierunek", 0))


def parse_fare(fare: dict, pax: int, bag_total: int) -> dict | None:
    out, inb = fare.get("outbound"), fare.get("inbound")
    if not out or not inb:
        return None

    arrival = out["arrivalAirport"]
    out_dep = datetime.fromisoformat(out["departureDate"])
    inb_dep = datetime.fromisoformat(inb["departureDate"])
    nights = (inb_dep.date() - out_dep.date()).days
    total_pp = fare["summary"]["price"]["value"]
    family_total = round(total_pp * pax, 2)

    return {
        "airport": arrival["iataCode"],
        "city": arrival.get("city", {}).get("name") or arrival["name"],
        "airport_name": arrival["name"],
        "outbound": out["departureDate"],
        "inbound": inb["departureDate"],
        "nights": nights,
        "price_per_person": round(total_pp, 2),
        "currency": fare["summary"]["price"]["currencyCode"],
        "family_total": family_total,
        "baggage_est_pln": bag_total,
        "family_total_with_bags": round(family_total + bag_total, 2),
    }


def collect_flights(cfg: dict) -> tuple[list[dict], list[str]]:
    """Zwraca (kierunki posortowane po cenie, błędy)."""
    pax = pax_count(cfg)
    bag_total = baggage_estimate(cfg)
    by_airport: dict[str, dict] = {}
    errors: list[str] = []

    for country_pl in cfg["kierunki"]["kraje"]:
        code = COUNTRY_CODES.get(country_pl)
        if not code:
            errors.append(f"Nieznany kraj w configu: {country_pl}")
            continue
        print(f"  szukam lotów: {country_pl} ({code})...", flush=True)
        try:
            fares = fetch_country_fares(cfg, code)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            errors.append(f"{country_pl}: błąd pobierania ({e})")
            continue

        for fare in fares:
            parsed = parse_fare(fare, pax, bag_total)
            if not parsed:
                continue
            dest = by_airport.setdefault(
                parsed["airport"],
                {
                    "airport": parsed["airport"],
                    "city": parsed["city"],
                    "airport_name": parsed["airport_name"],
                    "country": country_pl,
                    "options": [],
                },
            )
            dest["options"].append(parsed)

    destinations = []
    for dest in by_airport.values():
        dest["options"].sort(key=lambda o: o["price_per_person"])
        dest["options"] = dest["options"][:OPTIONS_PER_DESTINATION]
        dest["cheapest_family_total"] = dest["options"][0]["family_total"]
        destinations.append(dest)

    destinations.sort(key=lambda d: d["cheapest_family_total"])
    return destinations, errors


def main() -> int:
    cfg = load_config()
    pax = pax_count(cfg)

    print(f"Wylot: {cfg['wylot']['lotnisko']}, "
          f"{cfg['daty']['od']} – {cfg['daty']['do']}, "
          f"{cfg['daty']['min_nocy']}-{cfg['daty']['max_nocy']} nocy, {pax} osób")

    destinations, errors = collect_flights(cfg)
    for err in errors:
        print(f"  UWAGA: {err}", file=sys.stderr)

    if not destinations:
        print("Brak wyników lotów — sprawdź daty/lotnisko w config.toml.", file=sys.stderr)
        return 1

    results = {
        "file_role": "POŚREDNI — półprodukt dla find_lodging.py; finalne wyniki "
                     "znajdziesz w lodging.finalny.json (pełne dane) "
                     "i ranking.finalny.json (ranking).",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": {
            "airport": cfg["wylot"]["lotnisko"],
            "date_from": cfg["daty"]["od"].isoformat(),
            "date_to": cfg["daty"]["do"].isoformat(),
            "nights": [cfg["daty"]["min_nocy"], cfg["daty"]["max_nocy"]],
            "adults": cfg["osoby"]["dorosli"],
            "children_ages": cfg["osoby"]["dzieci"],
            "pax": pax,
        },
        "source": "Ryanair fare finder API (services-api.ryanair.com)",
        "note": "Ceny za 1 osobę w PLN; family_total = cena × liczba osób. "
                "Tylko Ryanair — Wizz Air i inni przewoźnicy nieuwzględnieni.",
        "errors": errors,
        "destinations": destinations,
    }

    FLIGHTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nZapisano {FLIGHTS_PATH.name}")

    bag_total = baggage_estimate(cfg)
    bag_info = (f" | bagaż: {cfg['loty']['bagaz_rejestrowany_szt']} szt "
                f"× 2 kierunki × {cfg['loty']['bagaz_pln_szt_kierunek']} zł = {bag_total} zł"
                if bag_total else "")
    print(f"\nKierunki wg ceny lotów dla {pax} osób (najtańsza opcja){bag_info}:")
    for dest in destinations:
        best = dest["options"][0]
        print(f"  {best['family_total']:>8.0f} zł | z bagażem {best['family_total_with_bags']:>8.0f} zł  "
              f"{dest['city']:<18} {dest['country']:<10} "
              f"{best['outbound'][:10]} → {best['inbound'][:10]} ({best['nights']} nocy)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
