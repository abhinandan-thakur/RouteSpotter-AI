# Fuel Route Planner

Django API that calculates a driving route and selects cost-effective fuel stops using the fuel-price data provided in the assessment.

Route geometry and driving distance come from the public OSRM routing API. Start and finish locations are resolved using Open-Meteo geocoding.

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

The import command loads the fuel-price CSV into the database and keeps the lowest listed price for duplicate OPIS IDs.

The `--geocode` option resolves each distinct US city/state once and stores the resulting coordinates. This means fuel stations do not need to be geocoded during every route request.

Without `--geocode`, imported fuel stations do not have coordinates and cannot be used for route planning. The initial geocoding step is a one-time network operation and may take some time for the full dataset.

The project can use SQLite for local development. Set `DB_ENGINE=sqlite` to explicitly use SQLite.

To use PostgreSQL, configure:

```text
DB_NAME
DB_USER
DB_PASSWORD
DB_HOST
DB_PORT
```

in the environment or `.env` file.

## API

### `POST /api/v1/`

Example request:

```json
{
  "start": "Austin, TX",
  "finish": "Dallas, TX"
}
```

A successful response contains:

- Start and finish coordinates
- Route geometry as a GeoJSON `LineString`
- Total route distance
- Selected fuel stops
- Fuel price at each stop
- Gallons purchased
- Cost of each fuel purchase
- Total estimated fuel cost

For a normal uncached request, the application performs two geocoding lookups for the start and finish locations and one OSRM routing lookup. Fuel-station matching and optimization are performed locally.

## Fuel Stop Optimization

The vehicle is assumed to:

- Start with a full tank
- Have a maximum range of 500 miles
- Achieve 10 miles per gallon
- Refuel in 0.1-gallon increments
- Consider fuel stations within 20 miles of the calculated route

The optimizer first maps candidate fuel stations to positions along the route.

It then searches states consisting of the current location and remaining vehicle range. A Dijkstra-style shortest-path search is used to find a cost-effective sequence of fuel purchases while respecting the 500-mile range constraint.

Fuel already available in the starting tank is not included in `fuel_cost_usd`.

The station offset from the route is estimated using straight-line distance. Actual road detours may therefore differ from the reported `detour_miles`.

## Performance

Geocoding results and route results are cached to avoid repeating external requests for identical locations and routes.

Fuel-station data is stored locally in the database, so the route-planning request does not require external API calls for individual fuel stations.

The public OSRM demo server and Open-Meteo geocoding service are used for the assessment/demo and should not be considered production SLA-backed services.

## Tests

Run the Django test suite with:

```bash
python manage.py test locator
```

## Demo

Loom video:

https://www.loom.com/share/79e2489eb2bf4e8b895077a5fcd3035f
