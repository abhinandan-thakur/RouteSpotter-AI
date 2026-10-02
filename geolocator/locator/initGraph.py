import csv
from collections import defaultdict
from pathlib import Path

import requests
from django.conf import settings

from .models import FuelStop


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


def geocode_city(city, state):
    response = requests.get(
        GEOCODING_URL,
        params={"name": f"{city}, {state}", "count": 1, "language": "en", "format": "json"},
        timeout=10,
    )
    response.raise_for_status()
    results = response.json().get("results", [])
    match = next((result for result in results if result.get("country_code") == "US"), None)
    if not match:
        return None
    return match["latitude"], match["longitude"]

def import_fuel_stops(csv_path=None, geocode=False):
    # geting csv path for what?
    csv_path = Path(csv_path or settings.BASE_DIR / "fuel-prices-for-be-assessment.csv")
    offers = {}
    coordinates = {}
    print("Starting process...")
    count = 0
    # opening csv file
    with csv_path.open(newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            print(count)
            count=count+1
            opis_id = int(row["OPIS Truckstop ID"])
            city = row["City"].strip()
            state = row["State"].strip()
            key = opis_id
            offer = {
                "opis_id": opis_id,
                "name": row["Truckstop Name"].strip(),
                "address": row["Address"].strip(),
                "city": city,
                "state": state,
                "rack_id": int(row["Rack ID"]),
                "price_per_gallon": float(row["Retail Price"]),
            }

            if key not in offers or offer["price_per_gallon"] < offers[key]["price_per_gallon"]:
                offers[key] = offer

            if geocode and state != "AB" and (city, state) not in coordinates:
                already_known = FuelStop.objects.filter(city=city, state=state, latitude__isnull=False, longitude__isnull=False).first()
                if already_known:
                    coordinates[(city,state)] = (already_known.latitiude, already_known.longitude)
                else:
                    try:
                        # api call
                        coordinates[(city, state)] = geocode_city(city, state)
                    except requests.RequestException:
                        # good fallback
                        coordinates[(city, state)] = None
    
    print("made all offers...")

    for offer in offers.values():
        coords = coordinates.get((offer["city"], offer["state"]))
        if coords:
            offer["latitude"], offer["longitude"] = coords
        
        FuelStop.objects.update_or_create(opis_id=offer.pop("opis_id"), defaults=offer)

    return len(offers)
