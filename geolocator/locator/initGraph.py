import csv
from collections import defaultdict
from pathlib import Path

import requests
from django.conf import settings

from .models import FuelStop


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


# LGTM
def geocode_city(city, state):
    # check this params and timout parameter let me check it
    response = requests.get(
        GEOCODING_URL,
        params={"name": f"{city}, {state}", "count": 1, "language": "en", "format": "json"},
        timeout=10,
    )
    # what does raise for status do?
    # do i need anything beside latitude and longitude?
    # but as of now the logic seems good only implementation problem if any?
    response.raise_for_status()
    results = response.json().get("results", [])
    match = next((result for result in results if result.get("country_code") == "US"), None)
    if not match:
        return None
    return match["latitude"], match["longitude"]

# TODO Understand this later
# ?btw, what this function is actually doing no idea?
# A - accurate
# S - safe, secure
# M - mantainable, modular
# R - robust, reliable, readable
# test - write a test for it?
# ! is it checking whether a row exist in db or not fuelstop no... i guess that will result in useless api calls
# ! because there is no way of preventing  geocode city
# ! shouldn't state == "US" i mean  be better than state != "AB" but in this case we only have on db so we can let it slide...
# !
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
            # in every row we are iterating
            # and storing var id, city, state, offer
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

            # ? what does this mean?
            # shouldn't here be && since we don't key == ofers and offer[] < offers[key]
            # no it should be or
            # * because if we don't have that key add that key or if that orffer[key] > than what we have update it
            if key not in offers or offer["price_per_gallon"] < offers[key]["price_per_gallon"]:
                offers[key] = offer

            # so if we are applying for api calls and state is not AB why AB?
            # and city,state is not cache then do this?
            # WHY AB? what if i remove that?
            # if canada is a problem why not remove all?
            # so we make a list of all the offers or all the rows
            # but if we already know we can tell if there is a required update in the lat and long of that city, state
            # if we api calls is allowed and state is usa and city,state not in corr
            # without making an api call
            # well api calls limit take priority here
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

    # ? i don't think we are checking whether the first result is in berlin or france just adding it 
    # ? new mexico is in mexica and usa i guess wouldn't this fail in edge cases
    # what is offers first offers is a dict and we are storing each offer value with its key
    # offers is the list of all the values in the dataset with its key as opis_id
    for offer in offers.values():
        coords = coordinates.get((offer["city"], offer["state"]))
        # so we are storing the value of an offer city, state in a coods
        # if coords exist
        # ? wtf? why why does it even do?
        if coords:
            offer["latitude"], offer["longitude"] = coords
        # and then we are updating fuelStop.objects.update
        
        FuelStop.objects.update_or_create(opis_id=offer.pop("opis_id"), defaults=offer)

    return len(offers)
