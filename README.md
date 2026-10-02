Loom vio = https://www.loom.com/share/79e2489eb2bf4e8b895077a5fcd3035f

# Fuel Route Planner

Django API for driving routes with fuel stops chosen from the assessment CSV. Route geometry comes from the public OSRM demo server; start and finish locations are resolved with Open-Meteo.

## Setup

```bash
export DB_ENGINE=sqlite
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py import_fuel_stops --geocode
python manage.py runserver
```

The import command keeps the lowest listed price for duplicate OPIS IDs. `--geocode` resolves each distinct US city/state once and stores coordinates, so route requests do not geocode fuel stations. Without `--geocode`, imported rows have no coordinates and cannot be used for route planning. Geocoding is a one-time network operation and may take a while for the full dataset.

The project uses SQLite when `DB_NAME` is unset. Set `DB_ENGINE=sqlite` to force SQLite when a local `.env` contains PostgreSQL settings. Set `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` to use PostgreSQL instead.

## API

`POST /api/v1/`

```json
{
  "start": "Austin, TX",
  "finish": "Dallas, TX"
}
```

A successful response includes a GeoJSON `LineString`, route distance, selected fuel stops, purchased gallons, and estimated fuel cost. Requests use two Open-Meteo lookups and one OSRM route lookup; fuel-stop matching and optimization run locally.

The optimizer searches route-position and remaining-range states. It assumes the vehicle starts with a full 500-mile tank, averages 10 miles per gallon, can refuel in 0.1-gallon increments, and considers stations within 20 miles of the route. The estimated straight-line station offset is included for driving to and back from each selected stop; actual road detours may differ. Fuel already in the starting tank is not included in `fuel_cost_usd`. The public OSRM demo server and Open-Meteo are suitable for an assessment/demo, not a production SLA.

## Tests

```bash
python manage.py test locator
```
