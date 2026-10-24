"""Tests for trip_time (task 10.2, Requirement 16.3).

Covers:
  - a short clear-day trip: small minutes, clear_day_minutes ~= minutes,
    leave_earlier_by_min ~= 0, broken False
  - the same trip in a blizzard: minutes >= clear_day_minutes and
    leave_earlier_by_min > 0
  - route_nodes is a valid path (consecutive nodes adjacent in the drive graph)
    from the origin-snapped node to the dest-snapped node
  - an unroutable / degenerate case: inf minutes and broken True
  - elevators_out surfaces a warning naming the stop; empty -> no warnings

These run against the cached study-area drive graph (data/cache/drive.graphml).
"""
from __future__ import annotations

import math

import pytest

from config.params import BROKEN_MINUTES
from src.contract import Scenario, trip_time
from src.sim.simulate import _get_graph, _nearest_node

# Two points inside the Longwood/Fenway study area (hospital locations) that are
# a short drive apart under clear-day conditions.
BIDMC = (42.33979095, -71.10515721024117)       # Beth Israel East Campus
CHILDRENS = (42.33717145, -71.10567907164955)   # Boston Children's


def _scenario(snow_inches: float, *, elevators_out=None,
              parking_compliance: float = 0.6,
              green_e_suspended: bool = False) -> Scenario:
    return {
        "snow_inches": snow_inches,
        "start_hour": 7,
        "duration_hours": 10,
        "parking_compliance": parking_compliance,
        "green_e_suspended": green_e_suspended,
        "elevators_out": list(elevators_out or []),
    }


# ---------------------------------------------------------------- clear day

def test_clear_day_trip_is_small_and_matches_baseline():
    # A true clear day: no snow, full parking compliance, E branch running --
    # the exact conditions the clear-day baseline uses, so the storm run and the
    # baseline must coincide and leave_earlier must be ~0.
    sc = _scenario(0.0, parking_compliance=1.0, green_e_suspended=False)
    hour = 10
    res = trip_time(BIDMC, CHILDRENS, sc, hour)

    assert math.isfinite(res["minutes"])
    assert res["minutes"] < BROKEN_MINUTES          # a short hop, not broken
    assert res["broken"] is False
    assert res["clear_day_minutes"] == pytest.approx(res["minutes"], abs=1e-6)
    assert res["leave_earlier_by_min"] == pytest.approx(0.0, abs=1e-6)
    assert res["warnings"] == []


def test_zero_snow_with_parked_cars_is_near_but_not_below_clear_day():
    # With snow 0 but imperfect parking compliance, parked cars on priority
    # routes still cost a little capacity, so the storm trip is >= the clear-day
    # baseline and leave_earlier is never negative (Requirement 16.3).
    sc = _scenario(0.0, parking_compliance=0.6)
    res = trip_time(BIDMC, CHILDRENS, sc, 10)
    assert res["minutes"] >= res["clear_day_minutes"] - 1e-9
    assert res["leave_earlier_by_min"] >= 0.0


# ---------------------------------------------------------------- blizzard

def test_blizzard_trip_is_slower_than_clear_day():
    sc = _scenario(24.0)      # heavy blizzard
    hour = 17                 # late in the storm, rush hour
    res = trip_time(BIDMC, CHILDRENS, sc, hour)

    # Even if unreachable (inf), inf >= clear_day holds; if reachable it is
    # strictly slower, so leave_earlier is positive.
    assert res["minutes"] >= res["clear_day_minutes"]
    if math.isfinite(res["minutes"]):
        assert res["leave_earlier_by_min"] > 0.0
        assert res["leave_earlier_by_min"] == pytest.approx(
            res["minutes"] - res["clear_day_minutes"], abs=1e-6
        )


def test_leave_earlier_is_never_negative():
    # Clear-day run has snow 0; forcing snow 0 means storm == clear day, so the
    # difference is exactly 0 and must not be reported negative.
    res = trip_time(BIDMC, CHILDRENS, _scenario(0.0), 12)
    assert res["leave_earlier_by_min"] >= 0.0


# ---------------------------------------------------------------- route validity

def test_route_nodes_form_a_valid_path():
    sc = _scenario(0.0)
    hour = 10
    res = trip_time(BIDMC, CHILDRENS, sc, hour)

    G = _get_graph()
    o_node = _nearest_node(G, BIDMC[0], BIDMC[1])
    d_node = _nearest_node(G, CHILDRENS[0], CHILDRENS[1])

    route = res["route_nodes"]
    assert route, "expected a non-empty route on a clear day"
    assert route[0] == o_node
    assert route[-1] == d_node
    # Every consecutive pair is an edge in the drive graph.
    for a, b in zip(route, route[1:]):
        assert G.has_edge(a, b), f"nodes {a} -> {b} are not adjacent in the graph"


# ---------------------------------------------------------------- unroutable

def test_inf_minutes_implies_broken_and_empty_route(monkeypatch):
    # Deterministically exercise the no-route branch by forcing the shortest
    # path helper to report no route, independent of the real graph topology.
    import src.sim.simulate as sim

    monkeypatch.setattr(sim, "_shortest_minutes",
                        lambda R, s, d: (math.inf, []))
    res = sim.trip_time(BIDMC, CHILDRENS, _scenario(0.0), 10)
    assert res["minutes"] == math.inf
    assert res["broken"] is True
    assert res["route_nodes"] == []
    assert res["leave_earlier_by_min"] == 0.0


def test_broken_when_storm_exceeds_threshold(monkeypatch):
    # Force storm minutes just over the broken threshold; clear day small.
    import src.sim.simulate as sim

    calls = {"n": 0}

    def fake_shortest(R, s, d):
        calls["n"] += 1
        # first call is the storm route, second is the clear-day route
        if calls["n"] == 1:
            return BROKEN_MINUTES + 5.0, [s, d]
        return 10.0, [s, d]

    monkeypatch.setattr(sim, "_shortest_minutes", fake_shortest)
    res = sim.trip_time(BIDMC, CHILDRENS, _scenario(20.0), 17)
    assert res["broken"] is True
    assert res["minutes"] == BROKEN_MINUTES + 5.0
    assert res["leave_earlier_by_min"] == pytest.approx(
        (BROKEN_MINUTES + 5.0) - 10.0
    )


# ---------------------------------------------------------------- elevators

def test_elevators_out_produces_named_warning():
    sc = _scenario(0.0, elevators_out=["place-longw"])
    res = trip_time(BIDMC, CHILDRENS, sc, 10)
    assert res["warnings"] == ["Elevator out at Longwood"]


def test_multiple_elevators_out_each_warned():
    sc = _scenario(0.0, elevators_out=["place-longw", "place-fenwy"])
    res = trip_time(BIDMC, CHILDRENS, sc, 10)
    assert "Elevator out at Longwood" in res["warnings"]
    assert "Elevator out at Fenway" in res["warnings"]
    assert len(res["warnings"]) == 2


def test_unknown_elevator_id_falls_back_to_raw_id():
    sc = _scenario(0.0, elevators_out=["place-does-not-exist"])
    res = trip_time(BIDMC, CHILDRENS, sc, 10)
    assert res["warnings"] == ["Elevator out at place-does-not-exist"]


def test_empty_elevators_out_has_no_warnings():
    sc = _scenario(0.0, elevators_out=[])
    res = trip_time(BIDMC, CHILDRENS, sc, 10)
    assert res["warnings"] == []
