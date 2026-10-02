import math
import heapq
import hashlib
from concurrent.futures import ThreadPoolExecutor

import requests
from django.core.cache import cache

from .models import FuelStop


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
ROUTING_URL = "https://router.project-osrm.org/route/v1/driving"
MAX_RANGE_MILES = 500
MILES_PER_GALLON = 10
MAX_DETOUR_MILES = 20
GEOCODE_CACHE_SECONDS = 24 * 60 * 60
ROUTE_CACHE_SECONDS = 60*60


class RoutePlanningError(Exception):
    pass

#imtersting storing cache key in sha256?
def _cache_key(namespace, value):
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"locator:{namespace}:v1:{digest}"


# why redundancy?
# geocode_city() is doing the same thing?
# def geocode_city(city, state):
#     # check this params and timout parameter let me check it
#     response = requests.get(
#         GEOCODING_URL,
#         params={"name": f"{city}, {state}", "count": 10, "language": "en", "format": "json"},
#         timeout=10,
#     )
#     # what does raise for status do?
#     # do i need anything beside latitude and longitude?
#     # but as of now the logic seems good only implementation problem if any?
#     response.raise_for_status()
#     results = response.json().get("results", [])
#     match = next((result for result in results if result.get("country_code") == "US"), None)
#     if not match:
#         return None
#     return match["latitude"], match["longitude"]

# ! the only difference is that isn't city,state we are sending query?
# ! okay this seems redundancy then a side case
#LGTM
def geocode_location(query):
    # storing a cacke key and its key is this
    cache_key = _cache_key("geocode", query.strip().casefold())
    cached_coordinates = cache.get(cache_key)
    if cached_coordinates is not None:
        return cached_coordinates

    response = requests.get(
        GEOCODING_URL,
        params={"name": query, "count": 10, "language": "en", "format": "json"},
        timeout=10,
    )
    response.raise_for_status()
    results = response.json().get("results", [])
    match = next((result for result in results if result.get("country_code") == "US"), None)
    if not match:
        raise RoutePlanningError(f"Could not find a US location for '{query}'.")
    coordinates = (match["latitude"], match["longitude"])
    # Geocoded coordinates are stable, so reuse them instead of repeating external lookups.
    cache.set(cache_key, coordinates, timeout=GEOCODE_CACHE_SECONDS)
    return coordinates


# * so we are using the osrm routing public api
# * return the [all the points making up that route][distance in miles thats why 1609.344]
# * LGTM
# so this is returning the distance of the patth the road from start to finish
def get_route(start, finish):
    route_key = f"{start[0]},{start[1]}:{finish[0]},{finish[1]}"
    cache_key = _cache_key("route", route_key)
    cached_route = cache.get(cache_key)
    if cached_route is not None:
        return cached_route

    url = f"{ROUTING_URL}/{start[1]},{start[0]};{finish[1]},{finish[0]}"
    response = requests.get(
        url,
        # A compact path keeps station projection fast while OSRM retains the full route distance.
        params={"overview": "simplified", "geometries": "geojson", "steps": "false"},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != "Ok" or not payload.get("routes"):
        raise RoutePlanningError("The routing service could not find a drivable route.")
    # what is in payload response .json()
    # why we are dividing it by 1609.344?
    # TODO i have to confirm that this return is correct
    route = payload["routes"][0]
    result = route["geometry"]["coordinates"], route["distance"] / 1609.344
    # Cache route geometry, but rebuild the fuel plan each time from current station prices.
    cache.set(cache_key, result, timeout=ROUTE_CACHE_SECONDS)
    return result


# * LGTM
# and this is returnign the displacement from the start to finish why
# ? why? though? the code is right but why we need it ?
def _distance_miles(first, second):
    # so we are convertin latitude and longitude from degree to radian why?
    # lets see...
    lat1, lon1 = math.radians(first[1]), math.radians(first[0])
    lat2, lon2 = math.radians(second[1]), math.radians(second[0])
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    EARTH_RADIUS = 3958.7613

    # ? are we making a triangle?
    # so we are using haversine formula? okay...
    haversine = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    haversine = min(1.0, max(0.0, haversine))
    c = 2*math.atan2(math.sqrt(haversine), math.sqrt(1-haversine))
    distance = EARTH_RADIUS*c

    return distance


def _project_to_route(point, coordinates, cumulative_miles):
    closest_distance = float("inf")
    closest_route_mile = 0.0

    # iterating through each and every drivable coordinates
    for index, (first, second) in enumerate(zip(coordinates, coordinates[1:])):
        reference_lat = math.radians((first[1] + second[1] + point[1]) / 3)
        scale_x = math.cos(reference_lat)
        segment_x = (second[0] - first[0]) * scale_x
        segment_y = second[1] - first[1]
        point_x = (point[0] - first[0]) * scale_x
        point_y = point[1] - first[1]
        segment_length_squared = segment_x * segment_x + segment_y * segment_y
        fraction = 0.0 if segment_length_squared == 0 else (point_x * segment_x + point_y * segment_y) / segment_length_squared
        fraction = min(1.0, max(0.0, fraction))
        projected = [first[0] + fraction * (second[0] - first[0]), first[1] + fraction * (second[1] - first[1])]
        distance = _distance_miles(point, projected)
        if distance < closest_distance:
            closest_distance = distance
            closest_route_mile = cumulative_miles[index] + fraction * (cumulative_miles[index + 1] - cumulative_miles[index])

    return closest_distance, closest_route_mile


def plan_fuel_stops(coordinates, route_miles, station_rows):
    # good fallback
    if not coordinates or route_miles <= 0:
        raise RoutePlanningError("The routing service returned an invalid route.")

    cumulative_miles = [0.0]
    # ? zip? i guess we are iterating from the second coordinate to the last with each iteration
    # * with lat and long
    # ? ant then appending it is cum_miles?
    # ? why what will it accomplish?
    # * so it is just a prefix sum of distance of every point in the route
    for first, second in zip(coordinates, coordinates[1:]):
        cumulative_miles.append(cumulative_miles[-1] + _distance_miles(first, second))
    geometry_miles = cumulative_miles[-1]
    if geometry_miles == 0:
        raise RoutePlanningError("The routing service returned an invalid route geometry.")
    # * now we are updating it...
    # route miles is the total drivable distance
    # mile is just iterating though cumulative miles
    # and geometry miles is last value 
    # ? i don't get the math of this or his approach what does it accomplish
    cumulative_miles = [mile * route_miles / geometry_miles for mile in cumulative_miles]

    candidates = []
    for station in station_rows:
        point = [station["longitude"], station["latitude"]]
        detour_miles, route_mile = _project_to_route(point, coordinates, cumulative_miles)
        if detour_miles <= MAX_DETOUR_MILES:
            candidates.append({**station, "route_mile": route_mile, "detour_miles": detour_miles})

    candidates.sort(key=lambda station: (station["route_mile"], station["price_per_gallon"]))
    distinct_candidates = []
    for candidate in candidates:
        if distinct_candidates and candidate["route_mile"] - distinct_candidates[-1]["route_mile"] < 0.1:
            if candidate["price_per_gallon"] < distinct_candidates[-1]["price_per_gallon"]:
                distinct_candidates[-1] = candidate
        else:
            distinct_candidates.append(candidate)

    nodes = [None, *distinct_candidates, None]
    positions = [0.0, *(station["route_mile"] for station in distinct_candidates), route_miles]
    destination_index = len(nodes) - 1
    reachable = []
    for source_index in range(len(nodes) - 1):
        destinations = []
        source_detour = nodes[source_index]["detour_miles"] if nodes[source_index] else 0.0
        for next_index in range(source_index + 1, len(nodes)):
            gap_miles = positions[next_index] - positions[source_index]
            destination_detour = nodes[next_index]["detour_miles"] if nodes[next_index] else 0.0
            if gap_miles + source_detour > MAX_RANGE_MILES:
                break
            leg_miles = gap_miles + source_detour + destination_detour
            if leg_miles > MAX_RANGE_MILES:
                continue
            destinations.append((next_index, math.ceil(leg_miles - 1e-9)))
        reachable.append(destinations)

    start_state = (0, MAX_RANGE_MILES)
    costs = {start_state: 0.0}
    previous = {}
    queue = [(0.0, start_state)]
    finish_state = None

    while queue:
        current_cost, state = heapq.heappop(queue)
        if current_cost != costs.get(state):
            continue
        node_index, remaining_range = state
        if node_index == destination_index:
            finish_state = state
            break

        transitions = []
        station = nodes[node_index]
        if station is not None and remaining_range < MAX_RANGE_MILES:
            transitions.append(((node_index, remaining_range + 1), station["price_per_gallon"] / MILES_PER_GALLON, "buy"))
        transitions.extend(
            ((next_index, remaining_range - range_required), 0.0, "drive")
            for next_index, range_required in reachable[node_index]
            if remaining_range >= range_required
        )

        for next_state, transition_cost, action in transitions:
            next_cost = current_cost + transition_cost
            if next_cost < costs.get(next_state, float("inf")):
                costs[next_state] = next_cost
                previous[next_state] = (state, action)
                heapq.heappush(queue, (next_cost, next_state))

    if finish_state is None:
        raise RoutePlanningError("No fuel-stop sequence can cover this route within the 500-mile range.")

    purchases = {}
    state = finish_state
    while state != start_state:
        prior_state, action = previous[state]
        if action == "buy":
            purchases[prior_state[0]] = purchases.get(prior_state[0], 0) + 1
        state = prior_state

    planned_stops = []
    for node_index, range_units_purchased in sorted(purchases.items()):
        station = nodes[node_index]
        if station is None or range_units_purchased == 0:
            continue
        gallons = range_units_purchased / MILES_PER_GALLON
        planned_stops.append({
            "opis_id": station["opis_id"],
            "name": station["name"],
            "address": station["address"],
            "city": station["city"],
            "state": station["state"],
            "latitude": station["latitude"],
            "longitude": station["longitude"],
            "price_per_gallon": station["price_per_gallon"],
            "route_mile": round(positions[node_index], 1),
            "detour_miles": round(station["detour_miles"], 1),
            "gallons_purchased": round(gallons, 1),
            "fuel_cost": round(gallons * station["price_per_gallon"], 2),
        })

    return planned_stops, round(costs[finish_state], 2)


def build_route_plan(start_query, finish_query):
    # These independent lookups run together to avoid serial network latency on a cache miss.
    with ThreadPoolExecutor(max_workers=2) as executor:
        start_future = executor.submit(geocode_location, start_query)
        finish_future = executor.submit(geocode_location, finish_query)
        start = start_future.result()
        finish = finish_future.result()
    # then we get the shortest path okay
    coordinates, route_miles = get_route(start, finish)
    # we create a list storing all the lattides and logitude of fuel statison which are not null
    stations = list(
        FuelStop.objects.filter(latitude__isnull=False, longitude__isnull=False)
        .values("opis_id", "name", "address", "city", "state", "latitude", "longitude", "price_per_gallon")
    )
    # good fallback
    if not stations:
        raise RoutePlanningError("No geocoded fuel stops are available. Run the fuel-stop import with --geocode first.")

    # ! plan_fuel_stops lets understand this function later first check where we are need that hypervise func?
    stops, fuel_cost = plan_fuel_stops(coordinates, route_miles, stations)
    return {
        "start": {"query": start_query, "latitude": start[0], "longitude": start[1]},
        "finish": {"query": finish_query, "latitude": finish[0], "longitude": finish[1]},
        "route": {
            "type": "LineString",
            "coordinates": coordinates,
            "distance_miles": round(route_miles, 1),
        },
        "fueling_plan": stops,
        "fuel_cost_usd": fuel_cost,
        "assumptions": {
            "miles_per_gallon": MILES_PER_GALLON,
            "maximum_range_miles": MAX_RANGE_MILES,
            "starting_tank": "full; fuel consumed before the first planned stop is excluded from fuel_cost_usd",
            "station_corridor_miles": MAX_DETOUR_MILES,
        },
    }
