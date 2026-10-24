---
inclusion: fileMatch
fileMatchPattern: ["src/adapters/**/*.py", "src/twin/**/*.py", "src/personas/**/*.py", "src/history/**/*.py", "src/validation/**/*.py", "mcp_server/**/*.py"]
---

# Data sources and conventions

Every source has one job: build the base twin, produce `Disruption`s, produce storm inputs, or produce persona attributes. See the table in design.md:
#[[file:.kiro/specs/longwood-storm-twin/design.md]]

## Study area
Bbox: north 42.350, south 42.330, east -71.085, west -71.115. Filter every source to this box (plus surrounding tracts for the Census personas).

## MBTA V3 API (`https://api-v3.mbta.com`)
- JSON:API format: data in `data[]`, related objects in `included[]`. Use `include=` to pull related stops/routes in one call.
- Key in header `x-api-key: $MBTA_API_KEY` (free; works without a key at low rate limits).
- Useful endpoints: `/alerts`, `/stops`, `/facilities` (filter type ELEVATOR), `/routes`, `/predictions`.
- Alert fields used: `effect`, `severity` (0–10), `active_period[]`, `informed_entity[]` (route, stop, direction_id, activities), `header`, `description`.
- Route ids: `Green-D`, `Green-E`; bus routes are numeric strings (look up which ones serve Longwood from GTFS, don't hard-code from memory).
- Static GTFS zip from the MBTA developers page; use `stops.txt`, `routes.txt`, `trips.txt`, `stop_times.txt`, `calendar*.txt`.

## National Weather Service (`https://api.weather.gov`)
- **Must send a `User-Agent` header** identifying the app and a contact, or requests are rejected.
- `/points/{lat},{lon}` → `properties.forecastGridData` URL.
- Grid data fields used: `snowfallAmount`, `windSpeed`, `windGust` (values are time series with ISO 8601 durations; units in `uom`).
- `/alerts/active?point={lat},{lon}`: use `event` (e.g. "Winter Storm Warning", "Blizzard Warning", "Wind Advisory"), `onset`, `ends`.

## Census ACS API (`https://api.census.gov/data/<year>/acs/acs5`)
- Boston is Suffolk County, MA (state 25, county 025). Query at tract level.
- Verify exact variable IDs in the published variable list before coding. Needed: households with no vehicle available; householders 65+ living alone; total households; population.

## Analyze Boston (CKAN, `https://data.boston.gov`)
- `api/3/action/datastore_search_sql` for 311 requests; filter by snow/plow-related case types (check the actual type names in the data first) and storm dates.
- Vision Zero crash records: from city 911 dispatch, updated about monthly; does not fully match the state crash database. Say this whenever the layer is shown.

## Other
- NOAA NDBC buoy 44013 realtime text feed: pressure (PRES), wind (WSPD, GST). Display only.
- Snow emergency routes: names from the City of Boston / Boston Police list; tag by street name and check visually.
- MassDOT real-time travel times: needs a form-based access request. Not used now.

## Adapter rules
- Every adapter returns `(result, fetched_at)` and never raises to callers; on failure return the last snapshot with `stale_since` set.
- Save one real response per endpoint in `tests/fixtures/` and test against it.
- Log endpoint names and counts only, never persona data.
