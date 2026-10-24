"""Tests for src/twin/transit.py (task 5.1, Requirement 1.5).

Validates the committed Green Line D/E stop cache: every stop sits inside the
study-area bbox, carries wheelchair accessibility and an elevator list, and the
derived step_free flag matches the MBTA wheelchair_boarding code. The test runs
offline against the committed cache (no live MBTA calls), matching the demo's
cache-first design.
"""
from __future__ import annotations

from config.params import BBOX
from src.twin.transit import load_transit_stops

GREEN_ROUTES = {"Green-D", "Green-E"}
STOP_KEYS = {
    "id", "name", "lat", "lon", "routes",
    "wheelchair_boarding", "elevators", "step_free",
}


def test_cache_loads_without_network():
    """load_transit_stops reads the committed cache and returns stops."""
    data = load_transit_stops()
    assert "fetched_at" in data
    assert isinstance(data["stops"], list)
    assert len(data["stops"]) >= 1


def test_every_stop_is_well_formed_and_in_bbox():
    stops = load_transit_stops()["stops"]
    ids = set()
    for s in stops:
        assert STOP_KEYS <= set(s), f"{s.get('id')} missing keys"
        # unique id
        assert s["id"] not in ids, f"duplicate id {s['id']}"
        ids.add(s["id"])
        # inside the study-area bbox
        assert BBOX["south"] <= s["lat"] <= BBOX["north"], s["id"]
        assert BBOX["west"] <= s["lon"] <= BBOX["east"], s["id"]
        # at least one Green-D / Green-E route, nothing else
        assert s["routes"], f"{s['id']} has no routes"
        assert set(s["routes"]) <= GREEN_ROUTES, s["routes"]


def test_accessibility_and_elevators_tagged():
    """Requirement 1.5: each stop has wheelchair_boarding, elevators and a
    step_free flag derived from the MBTA accessibility code (1 == accessible)."""
    stops = load_transit_stops()["stops"]
    for s in stops:
        assert s["wheelchair_boarding"] in (0, 1, 2), s["id"]
        assert isinstance(s["elevators"], list)
        assert all(isinstance(e, str) for e in s["elevators"])
        assert s["step_free"] == (s["wheelchair_boarding"] == 1), s["id"]


def test_covers_both_green_branches():
    routes = {r for s in load_transit_stops()["stops"] for r in s["routes"]}
    assert routes == GREEN_ROUTES
