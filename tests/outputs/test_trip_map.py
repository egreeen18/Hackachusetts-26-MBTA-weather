"""Tests for the trip route map (task 17, Requirements 11.1 / 11.2).

Covers that ``build_trip_map`` builds a folium map with a route drawn from real
``trip_time`` node ids under a storm scenario, and that it degrades gracefully
when the route is empty (home + destination only, no exception).
"""

from __future__ import annotations

from pathlib import Path

import folium
import pytest

from src.contract import DEFAULT_SCENARIO, trip_time
from src.outputs import map as citymap

GRAPH_CACHE = Path(__file__).resolve().parents[2] / "data" / "cache" / "drive.graphml"
HOSPITALS = Path(__file__).resolve().parents[2] / "data" / "cache" / "hospitals.json"

# Two study-area points (lat, lon) for the no-graph / empty-route cases.
HOME = (42.3457, -71.1041)
DEST = (42.3356, -71.1060)


# --------------------------------------------------------------------------- empty / no-graph


def test_build_trip_map_empty_route_without_graph():
    # No route nodes and no graph: still builds, shows home + dest only.
    m = citymap.build_trip_map([], graph=None, home_latlon=HOME, dest_latlon=DEST)
    assert isinstance(m, folium.Map)


def test_build_trip_map_empty_route_broken_flag():
    m = citymap.build_trip_map(
        [], graph=None, home_latlon=HOME, dest_latlon=DEST, broken=True
    )
    assert isinstance(m, folium.Map)


def test_route_latlons_empty_without_graph():
    assert citymap._route_latlons([1, 2, 3], graph=None) == []
    assert citymap._route_latlons([], graph=object()) == []


# --------------------------------------------------------------------------- real trip


def _two_hospital_coords():
    import json
    with HOSPITALS.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert len(data) >= 2, "need at least two hospitals"
    a = (data[0]["lat"], data[0]["lon"])
    b = (data[1]["lat"], data[1]["lon"])
    return a, b


def test_build_trip_map_with_real_route():
    """Build a trip map from a real trip_time route under a storm scenario."""
    if not GRAPH_CACHE.exists():
        pytest.skip("drive.graphml cache not present")
    if not HOSPITALS.exists():
        pytest.skip("hospitals.json cache not present")
    import osmnx as ox

    graph = ox.load_graphml(filepath=str(GRAPH_CACHE))
    home, dest = _two_hospital_coords()

    # A storm scenario so the trip is meaningfully slowed.
    scenario = dict(DEFAULT_SCENARIO)
    scenario["snow_inches"] = 14.0
    trip = trip_time(home, dest, scenario, hour=8)

    # Builds without exception, with or without a route.
    m = citymap.build_trip_map(
        route_nodes=trip["route_nodes"],
        graph=graph,
        home_latlon=home,
        dest_latlon=dest,
        broken=trip["broken"],
        minutes=trip["minutes"],
    )
    assert isinstance(m, folium.Map)

    # If a route was found, its node ids resolve to coordinates.
    if trip["route_nodes"]:
        coords = citymap._route_latlons(trip["route_nodes"], graph)
        assert len(coords) >= 2
        for lat, lon in coords:
            assert isinstance(lat, float) and isinstance(lon, float)
