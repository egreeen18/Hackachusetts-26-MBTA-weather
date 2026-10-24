"""Tests for the real run_simulation (task 6.3).

Covers Requirements 15.1 (minutes to nearest hospital, inf if unreachable),
15.2 (broken flag), 15.3 (KPIs), 16.1 (contract shapes) and 7.4 (label):

  - a clear day (snow=0) gives every edge capacity_factor 1.0 and finite,
    reasonable minutes to a hospital;
  - a blizzard raises minutes and pct_broken versus the clear day;
  - KPIs are internally consistent (avg over reachable origins only,
    n_unreachable counts the inf origins);
  - the minutes come from a single multi-source Dijkstra on the reversed graph.

These run against the cached drive graph (data/cache/drive.graphml) and the
cached hospitals (data/cache/hospitals.json), which the A tasks already built.
"""
from __future__ import annotations

import math

import networkx as nx
import pytest

from config.params import BROKEN_MINUTES
from src.contract import run_simulation
from src.sim import simulate

CLEAR = {
    "snow_inches": 0,
    "start_hour": 7,
    "duration_hours": 10,
    "parking_compliance": 1.0,
    "green_e_suspended": False,
    "elevators_out": [],
}

# A heavy storm that still keeps the network connected (side streets stay below
# the 12 in impassable threshold at the view hour). This is the regime where
# comparing *average* minutes to the clear day is meaningful.
BLIZZARD = {
    "snow_inches": 20,
    "start_hour": 7,
    "duration_hours": 10,
    "parking_compliance": 0.3,
    "green_e_suspended": True,
    "elevators_out": [],
}

# A collapse-level storm: enough snow that side streets pass the impassable
# threshold at the view hour and the network fragments (Requirement 3.7). Used
# to check that pct_broken and n_unreachable rise under extreme snow.
COLLAPSE = {
    "snow_inches": 24,
    "start_hour": 7,
    "duration_hours": 8,
    "parking_compliance": 0.3,
    "green_e_suspended": True,
    "elevators_out": [],
}

# A view hour in the thick of the storm for all scenarios.
HOUR = 12


# ---------------------------------------------------------------- shape / contract

def test_result_has_contract_shape():
    res = run_simulation(CLEAR, HOUR)
    assert set(res.keys()) == {"hour", "edges", "origins", "kpis", "label"}
    assert res["hour"] == HOUR
    assert res["label"] == "simulation estimate"  # Requirement 7.4

    assert res["edges"], "expected edge results"
    e = res["edges"][0]
    assert set(e.keys()) == {
        "u", "v", "key", "capacity_factor", "travel_time_s", "snow_on_road_in",
    }

    assert res["origins"], "expected origin results"
    o = res["origins"][0]
    assert set(o.keys()) == {
        "node", "lat", "lon", "minutes_to_hospital", "nearest_hospital", "broken",
    }

    k = res["kpis"]
    assert set(k.keys()) == {
        "pct_broken", "avg_minutes_to_hospital", "n_unreachable",
    }


def test_origins_are_intersections():
    # Origins come from street_count >= 3 nodes; the cached graph has 609.
    res = run_simulation(CLEAR, HOUR)
    G = simulate._get_graph()
    expected = {n for n, d in G.nodes(data=True)
                if int(d.get("street_count") or 0) >= 3}
    got = {o["node"] for o in res["origins"]}
    assert got == expected
    assert len(got) > 100  # sanity: this is a real, non-trivial network


# ---------------------------------------------------------------- clear day

def test_clear_day_all_capacity_one_and_finite_minutes():
    res = run_simulation(CLEAR, HOUR)

    # Snow is zero everywhere, so every edge keeps full capacity.
    for e in res["edges"]:
        assert e["capacity_factor"] == pytest.approx(1.0)
        assert math.isfinite(e["travel_time_s"])
        assert e["snow_on_road_in"] == 0.0

    reachable = [o for o in res["origins"]
                 if math.isfinite(o["minutes_to_hospital"])]
    assert reachable, "a clear day should reach some origins"

    # Minutes are small and positive for a ~2 km study area.
    for o in reachable:
        assert o["minutes_to_hospital"] >= 0.0
        assert o["minutes_to_hospital"] < 60.0
        assert o["nearest_hospital"]  # a non-empty hospital name

    assert res["kpis"]["avg_minutes_to_hospital"] < 15.0


def test_clear_day_nearest_hospital_is_a_real_hospital():
    from src.twin.hospitals import load_hospitals
    names = {h["name"] for h in load_hospitals()}
    res = run_simulation(CLEAR, HOUR)
    labelled = {o["nearest_hospital"] for o in res["origins"]
                if o["nearest_hospital"] is not None}
    assert labelled, "expected some origins to have a nearest hospital"
    assert labelled <= names


# ---------------------------------------------------------------- blizzard vs clear

def test_blizzard_raises_average_minutes():
    clear = run_simulation(CLEAR, HOUR)
    blizzard = run_simulation(BLIZZARD, HOUR)

    # A heavy-but-connected storm lengthens the average trip to a hospital.
    assert (blizzard["kpis"]["avg_minutes_to_hospital"]
            > clear["kpis"]["avg_minutes_to_hospital"])

    # No origin gets strictly faster in the blizzard (monotonicity sanity).
    clear_by_node = {o["node"]: o["minutes_to_hospital"] for o in clear["origins"]}
    for o in blizzard["origins"]:
        c = clear_by_node[o["node"]]
        if math.isfinite(c) and math.isfinite(o["minutes_to_hospital"]):
            assert o["minutes_to_hospital"] >= c - 1e-6


def test_collapse_storm_raises_broken_and_unreachable():
    clear = run_simulation(CLEAR, HOUR)
    collapse = run_simulation(COLLAPSE, HOUR)

    # Extreme snow closes side streets (Req 3.7), fragmenting the network, so
    # more origins break and more become unreachable than on a clear day.
    assert collapse["kpis"]["pct_broken"] > clear["kpis"]["pct_broken"]
    assert collapse["kpis"]["n_unreachable"] > clear["kpis"]["n_unreachable"]


# ---------------------------------------------------------------- KPI consistency

@pytest.mark.parametrize("scenario", [CLEAR, BLIZZARD])
def test_kpis_internally_consistent(scenario):
    res = run_simulation(scenario, HOUR)
    origins = res["origins"]
    k = res["kpis"]

    reachable = [o["minutes_to_hospital"] for o in origins
                 if math.isfinite(o["minutes_to_hospital"])]
    unreachable = [o for o in origins
                   if not math.isfinite(o["minutes_to_hospital"])]
    broken = [o for o in origins if o["broken"]]

    # n_unreachable counts exactly the inf origins.
    assert k["n_unreachable"] == len(unreachable)

    # pct_broken matches the broken flags.
    assert k["pct_broken"] == pytest.approx(100.0 * len(broken) / len(origins))

    # avg is over reachable origins only.
    if reachable:
        assert k["avg_minutes_to_hospital"] == pytest.approx(
            sum(reachable) / len(reachable)
        )
        assert math.isfinite(k["avg_minutes_to_hospital"])

    # every unreachable origin is also broken; every broken origin is either
    # unreachable or over the threshold (Requirement 15.2).
    for o in unreachable:
        assert o["broken"]
    for o in broken:
        assert (not math.isfinite(o["minutes_to_hospital"])
                or o["minutes_to_hospital"] > BROKEN_MINUTES)


# ---------------------------------------------------------------- single Dijkstra

def test_minutes_match_single_multi_source_dijkstra():
    """The reported minutes equal one multi_source_dijkstra on the reversed
    routing graph from the hospital nodes (design.md speed tip, Req 15.1)."""
    from src.twin.hospitals import load_hospitals

    scenario = BLIZZARD
    res = run_simulation(scenario, HOUR)

    # Rebuild the routing graph exactly as run_simulation does.
    G = simulate._get_graph()
    _edges, sim_times = simulate._edge_results_and_sim_times(G, scenario, HOUR)
    R = simulate._build_routing_graph(G, sim_times)

    sources = [int(h["node"]) for h in load_hospitals()
               if R.has_node(int(h["node"]))]
    lengths = nx.multi_source_dijkstra_path_length(
        R.reverse(copy=False), sources, weight=simulate.SIM_TIME_ATTR
    )

    for o in res["origins"]:
        node = o["node"]
        if node in lengths:
            assert o["minutes_to_hospital"] == pytest.approx(lengths[node] / 60.0)
        else:
            assert not math.isfinite(o["minutes_to_hospital"])


def test_impassable_edges_excluded_from_routing_graph():
    # Build a routing graph where one edge is impassable; it must be dropped.
    G = nx.MultiDiGraph()
    G.add_edge(1, 2, key=0)
    G.add_edge(2, 3, key=0)
    sim_times = {(1, 2, 0): 10.0, (2, 3, 0): math.inf}
    R = simulate._build_routing_graph(G, sim_times)
    assert R.has_edge(1, 2)
    assert not R.has_edge(2, 3)
