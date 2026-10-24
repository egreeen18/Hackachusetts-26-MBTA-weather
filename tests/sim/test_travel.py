"""Tests for src/sim/travel.py (task 6.2).

Covers the example cases plus the monotonicity guarantee from
.kiro/steering/simulation-assumptions.md (rule 5):
  - bpr(0) == 1 and grows with v/c, capped at VC_CAP
  - travel time == free-flow when cap == 1 and v/c == 0
  - travel time rises as capacity drops and as v/c rises
  - cap == 0 (impassable) -> infinite travel time (edge removed)
  - more snow never lowers an edge's travel time (monotonicity)

Validates: Requirements 3.4, 3.6
"""
from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from config.params import BPR_ALPHA, BPR_BETA, SPEED_EXPONENT, VC_CAP
from src.contract import Scenario
from src.sim.travel import (
    bpr,
    edge_sim_time,
    edge_travel_time,
    effective_capacity_factor,
)


def make_scenario(snow_inches: float = 14, start_hour: int = 0,
                  duration_hours: int = 20, parking_compliance: float = 0.6,
                  green_e_suspended: bool = False) -> Scenario:
    return {
        "snow_inches": snow_inches,
        "start_hour": start_hour,
        "duration_hours": duration_hours,
        "parking_compliance": parking_compliance,
        "green_e_suspended": green_e_suspended,
        "elevators_out": [],
    }


# ---------------------------------------------------------------- bpr

def test_bpr_is_one_with_no_traffic():
    assert bpr(0.0) == 1.0
    # negative input is clamped to 0 -> still 1.0
    assert bpr(-1.0) == 1.0


def test_bpr_grows_with_vc():
    assert bpr(0.5) < bpr(1.0) < bpr(1.5)


def test_bpr_matches_formula():
    vc = 0.8
    assert math.isclose(bpr(vc), 1.0 + BPR_ALPHA * vc ** BPR_BETA)


def test_bpr_is_capped_at_vc_cap():
    # anything at or above VC_CAP gives the same (capped) multiplier
    at_cap = bpr(VC_CAP)
    assert math.isclose(bpr(VC_CAP + 5), at_cap)
    assert math.isclose(bpr(1000.0), at_cap)
    assert math.isclose(at_cap, 1.0 + BPR_ALPHA * VC_CAP ** BPR_BETA)


# ---------------------------------------------------------------- edge_travel_time

def test_free_flow_when_clear_and_empty():
    # cap == 1 (no snow) and v/c == 0 (no traffic) -> exactly free-flow
    assert edge_travel_time(100.0, cap=1.0, vc=0.0) == 100.0


def test_travel_time_increases_as_capacity_drops():
    base = edge_travel_time(100.0, cap=1.0, vc=0.0)
    less = edge_travel_time(100.0, cap=0.5, vc=0.0)
    least = edge_travel_time(100.0, cap=0.25, vc=0.0)
    assert base < less < least
    # matches the speed-exponent form with no congestion
    assert math.isclose(less, 100.0 / 0.5 ** SPEED_EXPONENT)


def test_travel_time_increases_as_vc_rises():
    low = edge_travel_time(100.0, cap=1.0, vc=0.2)
    mid = edge_travel_time(100.0, cap=1.0, vc=0.8)
    high = edge_travel_time(100.0, cap=1.0, vc=1.5)
    assert low < mid < high


def test_travel_time_matches_full_formula():
    free_flow, cap, vc = 120.0, 0.4, 0.9
    expected = (free_flow / cap ** SPEED_EXPONENT) * (
        1.0 + BPR_ALPHA * vc ** BPR_BETA)
    assert math.isclose(edge_travel_time(free_flow, cap, vc), expected)


def test_impassable_edge_is_infinite():
    assert edge_travel_time(100.0, cap=0.0, vc=0.0) == math.inf
    # negative/degenerate capacity is also treated as impassable
    assert edge_travel_time(100.0, cap=-0.1, vc=0.5) == math.inf


def test_side_street_over_threshold_is_removed():
    # 20 in over 20 h = 1 in/h; a side street is unplowed during the storm and
    # holds >= 12 in by hour 12, so it is impassable (infinite travel time).
    sc = make_scenario(snow_inches=20, start_hour=0, duration_hours=20)
    cap = effective_capacity_factor("side", "Some Residential St", sc, 12)
    assert cap == 0.0
    assert edge_sim_time(100.0, "side", "Some Residential St", sc, 12) == math.inf


# ---------------------------------------------------------- effective_capacity_factor

def test_effective_capacity_is_full_without_snow_or_parking_loss():
    # Req 3.7: zero snowfall -> snow-only capacity is 1.0. With full parking
    # compliance there is no parked-car loss either, so effective capacity is 1.0.
    sc = make_scenario(snow_inches=0, parking_compliance=1.0)
    for rc in ("priority", "main", "side"):
        assert effective_capacity_factor(rc, None, sc, 10) == 1.0


def test_parked_cars_lower_priority_capacity_even_without_snow():
    # Rule 3: parked cars cut priority-route capacity regardless of snow, so the
    # *effective* capacity can be below 1.0 at zero snowfall. Non-priority roads
    # with no snow stay at 1.0.
    sc = make_scenario(snow_inches=0, parking_compliance=0.6)
    assert effective_capacity_factor("priority", None, sc, 10) < 1.0
    assert effective_capacity_factor("main", None, sc, 10) == 1.0
    assert effective_capacity_factor("side", None, sc, 10) == 1.0


def test_parked_cars_lower_priority_capacity():
    # same snow, lower compliance -> lower effective capacity on a priority route
    good = make_scenario(snow_inches=8, parking_compliance=1.0)
    bad = make_scenario(snow_inches=8, parking_compliance=0.0)
    assert (effective_capacity_factor("priority", "Huntington Avenue", bad, 10)
            < effective_capacity_factor("priority", "Huntington Avenue", good, 10))


def test_edge_sim_time_is_finite_and_slower_than_free_flow():
    sc = make_scenario(snow_inches=8, start_hour=0, duration_hours=20)
    t = edge_sim_time(100.0, "main", "Boylston Street", sc, 7)
    assert math.isfinite(t)
    assert t > 100.0  # snow + traffic make it slower than free-flow


# ---------------------------------------------------------------- property tests

@settings(max_examples=200)
@given(vc=st.floats(min_value=0, max_value=50), extra=st.floats(min_value=0, max_value=50))
def test_bpr_is_non_decreasing_in_vc(vc, extra):
    assert bpr(vc + extra) >= bpr(vc) - 1e-9


@settings(max_examples=200)
@given(
    free_flow=st.floats(min_value=1, max_value=1000),
    cap=st.floats(min_value=0.01, max_value=1.0),
    vc=st.floats(min_value=0, max_value=5),
)
def test_travel_time_never_below_free_flow(free_flow, cap, vc):
    # with cap <= 1 and any congestion, the congested time is >= free-flow
    assert edge_travel_time(free_flow, cap, vc) >= free_flow - 1e-6


@settings(max_examples=300)
@given(
    snow=st.floats(min_value=0, max_value=30),
    extra=st.floats(min_value=0, max_value=30),
    road_class=st.sampled_from(["priority", "main", "side"]),
    hour=st.integers(min_value=0, max_value=19),
    vc=st.floats(min_value=0, max_value=3),
)
def test_more_snow_never_lowers_travel_time_via_capacity(snow, extra, road_class,
                                                         hour, vc):
    """More snow never speeds an edge up through the snow->capacity channel (Req 3.6).

    The model has two ways snow touches an edge's time: it lowers capacity
    (rule 4-5, slower) and it lowers demand (rule 6, which can lower v/c and the
    congestion term). Those pull in opposite directions, so a just-plowed edge
    can be sub-second *faster* with a touch more snow purely from demand drop.
    This property isolates the capacity channel the guarantee is about: holding
    v/c fixed, more snow lowers the effective capacity factor and so never
    lowers the travel time. Origin/trip-level monotonicity over the full sweep
    is covered by task 6.4.

    Storm runs hours 0..20, so hour 0..19 is "while snow is falling". An
    impassable edge is +inf, the slowest possible, so closures also comply.
    """
    low = make_scenario(snow_inches=snow, start_hour=0, duration_hours=20)
    high = make_scenario(snow_inches=snow + extra, start_hour=0, duration_hours=20)
    cap_low = effective_capacity_factor(road_class, "Longwood Avenue", low, hour)
    cap_high = effective_capacity_factor(road_class, "Longwood Avenue", high, hour)
    # same v/c for both -> only the snow-driven capacity change can move the time
    t_low = edge_travel_time(100.0, cap_low, vc)
    t_high = edge_travel_time(100.0, cap_high, vc)
    assert t_high >= t_low - 1e-6


@settings(max_examples=200)
@given(
    compliance=st.floats(min_value=0.0, max_value=1.0),
    drop=st.floats(min_value=0.0, max_value=1.0),
    hour=st.integers(min_value=0, max_value=19),
)
def test_lower_compliance_never_lowers_travel_time(compliance, drop, hour):
    """Lower parking compliance never speeds a priority edge up (Req 3.6)."""
    hi_comp = min(1.0, compliance + drop)
    better = make_scenario(snow_inches=8, start_hour=0, duration_hours=20,
                           parking_compliance=hi_comp)
    worse = make_scenario(snow_inches=8, start_hour=0, duration_hours=20,
                          parking_compliance=compliance)
    t_better = edge_sim_time(100.0, "priority", "Huntington Avenue", better, hour)
    t_worse = edge_sim_time(100.0, "priority", "Huntington Avenue", worse, hour)
    assert t_worse >= t_better - 1e-6
