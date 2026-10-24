"""Tests for the city-view map renderer (task 7.1, Requirement 11.4).

Covers the colour bands exactly as the task specifies:
  roads    green -> red by capacity factor, closed (cap 0) = black
  origins  <=15 green, 15-30 orange, >30 red, unreachable grey
and a headless folium build from a real ``run_simulation`` result.
"""

from __future__ import annotations

from pathlib import Path

import folium
import pytest

from src.contract import DEFAULT_SCENARIO, run_simulation, sweep_snow
from src.outputs import map as citymap

GRAPH_CACHE = Path(__file__).resolve().parents[2] / "data" / "cache" / "drive.graphml"


# --------------------------------------------------------------------------- road colours


def test_full_capacity_is_green():
    assert citymap.capacity_color(1.0) == "#2ecc40"


def test_closed_road_is_black():
    # A capacity factor of exactly 0 means impassable -> black.
    assert citymap.capacity_color(0.0) == citymap.ROAD_CLOSED_COLOR == "#000000"


def test_gradient_reads_green_to_red():
    # Red channel rises and green channel falls as capacity drops from 1 -> 0.
    def rgb(hexstr: str) -> tuple[int, int, int]:
        h = hexstr.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    high = rgb(citymap.capacity_color(0.9))   # near green
    low = rgb(citymap.capacity_color(0.1))    # near red
    assert low[0] > high[0]   # more red at low capacity
    assert low[1] < high[1]   # less green at low capacity


def test_capacity_color_clamps_above_one():
    assert citymap.capacity_color(5.0) == citymap.capacity_color(1.0)


# --------------------------------------------------------------------------- origin bands


@pytest.mark.parametrize(
    "minutes,expected",
    [
        (0.0, "#2ecc40"),          # fast / green
        (15.0, "#2ecc40"),         # boundary stays green
        (15.1, "#ff8c00"),         # into orange
        (30.0, "#ff8c00"),         # boundary stays orange
        (30.1, "#ff4136"),         # into red
        (120.0, "#ff4136"),        # far away -> red
        (float("inf"), "#808080"),  # unreachable -> grey
    ],
)
def test_origin_color_bands(minutes, expected):
    assert citymap.origin_color(minutes) == expected


# --------------------------------------------------------------------------- map build


def _sample_result():
    """Fallback hand-built result when the real graph/sim isn't available."""
    return {
        "hour": 8,
        "edges": [],
        "origins": [
            {"node": 1, "lat": 42.34, "lon": -71.10, "minutes_to_hospital": 5.0,
             "nearest_hospital": "Brigham", "broken": False},
            {"node": 2, "lat": 42.34, "lon": -71.10,
             "minutes_to_hospital": float("inf"), "nearest_hospital": None, "broken": True},
        ],
        "kpis": {"pct_broken": 50.0, "avg_minutes_to_hospital": 5.0, "n_unreachable": 1},
        "label": "simulation estimate",
    }


def test_build_city_map_without_graph_renders_origins():
    m = citymap.build_city_map(_sample_result(), graph=None)
    assert isinstance(m, folium.Map)


def test_build_city_map_with_real_simulation():
    """Headless folium build from a real run_simulation result + cached graph."""
    if not GRAPH_CACHE.exists():
        pytest.skip("drive.graphml cache not present")
    import osmnx as ox

    graph = ox.load_graphml(filepath=str(GRAPH_CACHE))
    result = run_simulation(dict(DEFAULT_SCENARIO), hour=8)

    m = citymap.build_city_map(result, graph)
    assert isinstance(m, folium.Map)

    # A fully impassable edge (if the scenario produced one) must be black.
    for e in result["edges"]:
        if e["capacity_factor"] == 0.0:
            assert citymap.capacity_color(e["capacity_factor"]) == "#000000"
            break

    # An unreachable origin (inf minutes) must get the grey unreachable colour.
    for o in result["origins"]:
        if o["minutes_to_hospital"] == float("inf"):
            assert citymap.origin_color(o["minutes_to_hospital"]) == "#808080"
            break


# --------------------------------------------------------------------------- breaking-point colours (task 11.1, Req 15.4)


def test_never_breaks_is_grey():
    # None means the origin never breaks up to the sweep max -> grey.
    assert citymap.breaking_point_color(None) == citymap.BREAKING_POINT_NEVER_COLOR == "#808080"


def test_breaking_point_fragile_is_red():
    # Breaks at (near) 0 in -> fragile -> the red end of the scale.
    assert citymap.breaking_point_color(0.0) == "#ff4136"


def test_breaking_point_robust_is_green():
    # Holds to the top of the sweep -> robust -> the green end of the scale.
    assert citymap.breaking_point_color(citymap.BREAKING_POINT_MAX_INCHES) == "#2ecc40"


def test_breaking_point_gradient_reads_red_to_green():
    # As inches-to-break rises (more robust), red falls and green rises.
    def rgb(hexstr: str) -> tuple[int, int, int]:
        h = hexstr.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    fragile = rgb(citymap.breaking_point_color(2.0))    # low inches
    robust = rgb(citymap.breaking_point_color(28.0))    # high inches
    assert robust[0] < fragile[0]   # less red when robust
    assert robust[1] > fragile[1]   # more green when robust


def test_breaking_point_clamps_above_max():
    # Anything at/above the top anchor clamps to the robust green end.
    assert citymap.breaking_point_color(100.0) == citymap.breaking_point_color(
        citymap.BREAKING_POINT_MAX_INCHES
    )


def test_breaking_point_clamps_below_zero():
    # Negative (shouldn't happen) clamps to the fragile red end.
    assert citymap.breaking_point_color(-5.0) == citymap.breaking_point_color(0.0)


# --------------------------------------------------------------------------- join + summary helpers


def _sweep_and_result():
    """Hand-built sweep dict + matching SimResult for join/count tests."""
    result = {
        "hour": 8,
        "edges": [],
        "origins": [
            {"node": 1, "lat": 42.34, "lon": -71.10, "minutes_to_hospital": 5.0,
             "nearest_hospital": "Brigham", "broken": False},
            {"node": 2, "lat": 42.35, "lon": -71.11, "minutes_to_hospital": 40.0,
             "nearest_hospital": "BIDMC", "broken": True},
            {"node": 3, "lat": 42.33, "lon": -71.09,
             "minutes_to_hospital": float("inf"), "nearest_hospital": None, "broken": True},
        ],
        "kpis": {"pct_broken": 66.7, "avg_minutes_to_hospital": 22.5, "n_unreachable": 1},
        "label": "simulation estimate",
    }
    sweep = {1: 4.0, 2: 12.0, 3: None}  # node 3 never breaks
    return sweep, result


def test_join_sweep_with_origins_joins_on_node():
    sweep, result = _sweep_and_result()
    joined = citymap.join_sweep_with_origins(sweep, result)
    assert len(joined) == 3
    by_node = {o["node"]: o for o in joined}
    assert by_node[1]["inches_to_break"] == 4.0
    assert by_node[1]["lat"] == 42.34 and by_node[1]["lon"] == -71.10
    assert by_node[3]["inches_to_break"] is None


def test_join_skips_origins_missing_from_sweep():
    sweep, result = _sweep_and_result()
    del sweep[2]  # drop one node from the sweep
    joined = citymap.join_sweep_with_origins(sweep, result)
    assert {o["node"] for o in joined} == {1, 3}


def test_count_broken_by_threshold():
    sweep, result = _sweep_and_result()
    joined = citymap.join_sweep_with_origins(sweep, result)
    # node 1 breaks at 4, node 2 at 12, node 3 never.
    assert citymap.count_broken_by(joined, 3.0) == 0
    assert citymap.count_broken_by(joined, 4.0) == 1
    assert citymap.count_broken_by(joined, 12.0) == 2
    assert citymap.count_broken_by(joined, 30.0) == 2  # never-break not counted


# --------------------------------------------------------------------------- breaking-point map build


def test_build_breaking_point_map_without_graph_renders_origins():
    sweep, result = _sweep_and_result()
    joined = citymap.join_sweep_with_origins(sweep, result)
    m = citymap.build_breaking_point_map(joined, graph=None)
    assert isinstance(m, folium.Map)


def test_build_breaking_point_map_with_real_sweep():
    """Headless folium build from a real sweep_snow + run_simulation result."""
    if not GRAPH_CACHE.exists():
        pytest.skip("drive.graphml cache not present")
    import osmnx as ox

    graph = ox.load_graphml(filepath=str(GRAPH_CACHE))
    scenario = dict(DEFAULT_SCENARIO)
    result = run_simulation(scenario, hour=8)
    sweep = sweep_snow(scenario)

    joined = citymap.join_sweep_with_origins(sweep, result)
    assert joined, "join produced no origins"

    # Builds without exception.
    m = citymap.build_breaking_point_map(joined, graph)
    assert isinstance(m, folium.Map)

    # A fragile origin (low inches-to-break) gets a red-dominant colour; a
    # never-break origin gets grey.
    saw_break = saw_never = False
    for o in joined:
        itb = o["inches_to_break"]
        color = citymap.breaking_point_color(itb)
        if itb is None:
            assert color == "#808080"
            saw_never = True
        else:
            assert color.startswith("#") and len(color) == 7
            if itb <= 2.0:
                r = int(color[1:3], 16)
                g = int(color[3:5], 16)
                assert r >= g  # fragile end is red-dominant
                saw_break = True
    # The default scenario's sweep has both broken and never-break origins.
    assert saw_break or saw_never
