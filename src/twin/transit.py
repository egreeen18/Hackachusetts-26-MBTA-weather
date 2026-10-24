"""Green Line D/E stops with accessibility and elevators. Owner: A.

Task 5.1: Green Line D and E stops in the bbox with wheelchair accessibility and
elevator facility ids. (Requirement 1.5)

Pulls MBTA V3 /stops (Green-D, Green-E) filtered to the study-area bbox, records
each stop's wheelchair_boarding flag, then pulls /facilities (type ELEVATOR) per
parent station to attach elevator facility ids. Caches the result as
data/cache/transit_stops.json so the demo runs offline.

Per tech.md the twin layer must not import src/adapters/, so the small amount of
MBTA I/O needed to build the cache lives here (mirroring how network.py fetches
OSM directly). The live-alert adapter is a separate file, src/adapters/mbta.py.

Build once:
    python -m src.twin.transit
Then B/C load via load_transit_stops().

Output shape (data/cache/transit_stops.json):
    {
      "fetched_at": "<iso8601>",
      "stops": [
        {"id": "place-longw", "name": "Longwood", "lat": .., "lon": ..,
         "routes": ["Green-D"], "wheelchair_boarding": 1,
         "step_free": true, "elevators": ["facility-...", ...]},
        ...
      ]
    }
wheelchair_boarding: MBTA codes 0 = no info, 1 = accessible, 2 = not accessible.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

from config.params import BBOX

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
TRANSIT_JSON = CACHE_DIR / "transit_stops.json"

MBTA = "https://api-v3.mbta.com"
TIMEOUT = 10.0
GREEN_ROUTES = ["Green-D", "Green-E"]


def _mbta_headers() -> dict[str, str]:
    key = os.environ.get("MBTA_API_KEY")
    return {"x-api-key": key} if key else {}


def _in_bbox(lat: float, lon: float) -> bool:
    return (BBOX["south"] <= lat <= BBOX["north"]
            and BBOX["west"] <= lon <= BBOX["east"])


def _fetch_green_stops() -> list[dict]:
    """GET /stops for Green-D and Green-E, keep platform/station stops in bbox."""
    stops: dict[str, dict] = {}
    for route in GREEN_ROUTES:
        r = httpx.get(
            f"{MBTA}/stops",
            params={"filter[route]": route},
            headers=_mbta_headers(),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        for s in r.json().get("data", []):
            at = s["attributes"]
            lat = at.get("latitude")
            lon = at.get("longitude")
            if lat is None or lon is None or not _in_bbox(lat, lon):
                continue
            sid = s["id"]
            rec = stops.get(sid)
            if rec is None:
                rec = {
                    "id": sid,
                    "name": at.get("name"),
                    "lat": float(lat),
                    "lon": float(lon),
                    "routes": [],
                    "wheelchair_boarding": at.get("wheelchair_boarding", 0),
                    "parent_station": (
                        (s.get("relationships", {}) or {})
                        .get("parent_station", {})
                        .get("data", {}) or {}
                    ).get("id"),
                }
                stops[sid] = rec
            if route not in rec["routes"]:
                rec["routes"].append(route)
    return list(stops.values())


def _fetch_elevators(stop_id: str) -> list[str]:
    """GET /facilities?filter[type]=ELEVATOR for one stop; return facility ids."""
    r = httpx.get(
        f"{MBTA}/facilities",
        params={"filter[stop]": stop_id, "filter[type]": "ELEVATOR"},
        headers=_mbta_headers(),
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return [f["id"] for f in r.json().get("data", [])]


def build_transit_stops() -> dict:
    """Fetch Green D/E stops + accessibility + elevators; return the cache dict."""
    stops = _fetch_green_stops()

    # Attach elevators. Query the parent station where present (elevators are
    # listed against the station, not the platform), else the stop itself.
    seen: dict[str, list[str]] = {}
    for rec in stops:
        key = rec.get("parent_station") or rec["id"]
        if key not in seen:
            try:
                seen[key] = _fetch_elevators(key)
            except httpx.HTTPError:
                seen[key] = []
        rec["elevators"] = seen[key]
        rec["step_free"] = rec.get("wheelchair_boarding") == 1
        rec.pop("parent_station", None)

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "stops": stops,
    }


def save_transit_stops(data: dict, path: Path = TRANSIT_JSON) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load_transit_stops(path: Path = TRANSIT_JSON) -> dict:
    """Load cached transit stops; build and cache them if missing."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data = build_transit_stops()
    save_transit_stops(data, path)
    return data


def main() -> None:
    print("Fetching Green Line D/E stops in the study-area bbox ...")
    data = build_transit_stops()
    out = save_transit_stops(data)
    stops = data["stops"]
    print(f"Saved {len(stops)} stops -> {out}")
    for s in stops:
        flag = {0: "unknown", 1: "accessible", 2: "not accessible"}.get(
            s["wheelchair_boarding"], "?")
        print(f"  {s['id']:16s} {','.join(s['routes']):14s} "
              f"wheelchair={flag:14s} elevators={len(s['elevators'])}  {s['name']}")


if __name__ == "__main__":
    main()
