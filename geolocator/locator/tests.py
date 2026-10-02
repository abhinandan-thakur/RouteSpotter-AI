import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase

from locator.initGraph import import_fuel_stops
from locator.models import FuelStop
from locator.services import RoutePlanningError, build_route_plan, geocode_location, get_route, plan_fuel_stops


class FuelStopImportTests(TestCase):
	def test_import_deduplicates_ids_and_caches_city_coordinates(self):
		csv_content = (
			"OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"
			'42,Example Stop,"I-10, EXIT 2",Phoenix,AZ,930,3.50\n'
			'42,Example Stop,"I-10, EXIT 2",Phoenix  ,AZ,930,3.25\n'
		)
		with tempfile.TemporaryDirectory() as directory:
			csv_path = Path(directory) / "prices.csv"
			csv_path.write_text(csv_content, encoding="utf-8")
			with patch("locator.initGraph.geocode_city", return_value=(33.45, -112.07)) as geocode:
				imported = import_fuel_stops(csv_path, geocode=True)

		self.assertEqual(imported, 1)
		self.assertEqual(FuelStop.objects.count(), 1)
		stop = FuelStop.objects.get(opis_id=42)
		self.assertEqual(stop.price_per_gallon, 3.25)
		self.assertEqual(stop.latitude, 33.45)
		self.assertEqual(stop.address, "I-10, EXIT 2")
		geocode.assert_called_once_with("Phoenix", "AZ")


class FuelRoutingTests(SimpleTestCase):
	def setUp(self):
		self.route = [[0.0, 0.0], [10.0, 0.0]]
		self.stations = [
			{
				"opis_id": 1,
				"name": "Cheap stop",
				"address": "Exit 1",
				"city": "Route City",
				"state": "TX",
				"latitude": 0.0,
				"longitude": 4.0,
				"price_per_gallon": 2.0,
			},
			{
				"opis_id": 2,
				"name": "Expensive stop",
				"address": "Exit 2",
				"city": "Other City",
				"state": "TX",
				"latitude": 0.0,
				"longitude": 7.0,
				"price_per_gallon": 4.0,
			},
		]

	def test_finds_lowest_cost_feasible_stop_plan(self):
		stops, cost = plan_fuel_stops(self.route, 600, self.stations)

		self.assertEqual([stop["opis_id"] for stop in stops], [1])
		self.assertEqual(stops[0]["gallons_purchased"], 10.0)
		self.assertEqual(cost, 20.0)

	def test_reports_when_range_cannot_cover_route(self):
		with self.assertRaises(RoutePlanningError):
			plan_fuel_stops(self.route, 600, [])

	def test_fuel_cost_includes_station_detour_miles(self):
		station_off_route = {**self.stations[0], "latitude": 0.15}

		stops, cost = plan_fuel_stops(self.route, 600, [station_off_route])

		self.assertEqual(stops[0]["opis_id"], 1)
		self.assertGreater(stops[0]["detour_miles"], 10)
		self.assertGreater(cost, 20)

	@patch("locator.services.requests.get")
	def test_geocode_reuses_cached_coordinates(self, get):
		cache.clear()
		self.addCleanup(cache.clear)
		get.return_value.json.return_value = {
			"results": [{"country_code": "US", "latitude": 30.0, "longitude": -97.0}]
		}

		first = geocode_location("Cache Town, TX")
		second = geocode_location("Cache Town, TX")

		self.assertEqual(first, (30.0, -97.0))
		self.assertEqual(second, first)
		get.assert_called_once()

	@patch("locator.services.requests.get")
	def test_get_route_requests_simplified_geometry(self, get):
		cache.clear()
		self.addCleanup(cache.clear)
		get.return_value.json.return_value = {
			"code": "Ok",
			"routes": [{"geometry": {"coordinates": [[-120.0, 35.0], [-110.0, 35.0]]}, "distance": 1609.344}],
		}

		coordinates, distance = get_route((35.0, -120.0), (35.0, -110.0))
		cached_coordinates, cached_distance = get_route((35.0, -120.0), (35.0, -110.0))

		self.assertEqual(coordinates, [[-120.0, 35.0], [-110.0, 35.0]])
		self.assertEqual(distance, 1.0)
		self.assertEqual(cached_coordinates, coordinates)
		self.assertEqual(cached_distance, distance)
		self.assertEqual(get.call_args.kwargs["params"]["overview"], "simplified")
		get.assert_called_once()


class RouteApiTests(SimpleTestCase):
	def test_rejects_missing_locations(self):
		response = Client(enforce_csrf_checks=True).post(
			"/api/v1/", data=json.dumps({"start": "Austin"}), content_type="application/json"
		)

		self.assertEqual(response.status_code, 400)
		self.assertIn("finish", response.json()["error"])

	@patch("locator.views.build_route_plan", return_value={"fuel_cost_usd": 12.5})
	def test_returns_route_plan(self, build_route_plan):
		response = Client(enforce_csrf_checks=True).post(
			"/api/v1/",
			data=json.dumps({"start": "Austin, TX", "finish": "Dallas, TX"}),
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json(), {"fuel_cost_usd": 12.5})
		build_route_plan.assert_called_once_with("Austin, TX", "Dallas, TX")


class RoutePlanIntegrationTests(TestCase):
	@patch("locator.services.get_route", return_value=([[-120.0, 35.0], [-110.0, 35.0]], 600))
	@patch(
		"locator.services.geocode_location",
		side_effect=lambda query: {
			"Origin, TX": (35.0, -120.0),
			"Destination, TX": (35.0, -110.0),
		}[query],
	)
	def test_route_plan_uses_geocoded_database_stations(self, geocode, get_route):
		FuelStop.objects.create(
			opis_id=77,
			name="Route fuel",
			address="Highway exit",
			city="Route City",
			state="TX",
			rack_id=1,
			price_per_gallon=2.0,
			latitude=35.0,
			longitude=-116.0,
		)

		plan = build_route_plan("Origin, TX", "Destination, TX")

		self.assertEqual(plan["fueling_plan"][0]["opis_id"], 77)
		self.assertEqual(plan["fuel_cost_usd"], 20.0)
		self.assertEqual(plan["route"]["distance_miles"], 600.0)

		station = FuelStop.objects.get(opis_id=77)
		station.price_per_gallon = 4.0
		station.save(update_fields=["price_per_gallon"])
		updated_plan = build_route_plan("Origin, TX", "Destination, TX")

		self.assertEqual(updated_plan["fuel_cost_usd"], 40.0)
		self.assertEqual(geocode.call_count, 4)
		self.assertEqual(get_route.call_count, 2)
