"""Tests for the breaking-point sweep sweep_snow (task 10.1).

Covers Requirement 15.4: simulate snowfall from 0 to 30 inches in 2-inch steps
and record, for each origin, the first snowfall at which it breaks, or none.

What we check:
  - the sweep levels are 0, 2, ..., 30 (16 levels at the defaults);
  - the result keys are exactly the origin set run_simulation uses
    (intersections, street_count >= 3);
  - every value is None or one of the sweep levels;
  - an origin broken at 0 inches gets 0 (it was never fine);
  - monotonicity: once an origin is broken at some level it stays broken at
    every higher level, so the recorded first-break level is well defined and
    actually is the lowest level at which run_simulation reports it broken;
  - a lower first-break level means the origin broke at or before a
    higher-first-break origin (ordering sanity);
  - a clearly robust regime (near a hospital / modest snow) tends to break late
    or never, while extreme snow breaks more origins.

These run against the cached drive graph (data/cache/drive.graphml) and the
cached hospitals (data/cache/hospitals.json) that the A tasks built.
"""
from __future__ import annotations

import math

from config.params import BROKEN_MINUTES, SWEEP_MAX_IN, SWEEP_STEP_IN
from src.contract import run_simulation, sweep_snow
from src.sim import simulate

SCENARIO = {
    "snow_inches": 14,  # overridden by the sweep; only the other fields matter
    "start_hour": 7,
    "duration_hours": 10,
    "parking_compliance": 0.6,
    "green_e_suspended": False,
    "elevators_out": [],
}


def _expected_levels() -> list[int]:
    return list(range(0, SWEEP_MAX_IN + 1, SWEEP_STEP_IN))


# ---------------------------------------------------------------- levels

def test_sweep_levels_are_zero_to_thirty_by_two():
    levels = simulate.sweep_levels()
    assert levels == [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30]
    assert len(levels) == 16          # 16 reversed multi-source Dijkstra calls
    assert levels[0] == 0
    assert levels[-1] == SWEEP_MAX_IN


# ---------------------------------------------------------------- keys / values

def test_keys_match_origin_set():
    res = sweep_snow(SCENARIO)
    G = simulate._get_graph()
    expected = {n for n, d in G.nodes(data=True)
                if int(d.get("street_count") or 0) >= 3}
    assert set(res.keys()) == expected
    assert len(res) > 100  # a real, non-trivial network


def test_values_are_none_or_a_sweep_level():
    res = sweep_snow(SCENARIO)
    allowed = set(_expected_levels())
    for node, v in res.items():
        assert v is None or v in allowed, f"node {node} -> {v!r}"


def test_values_are_floats_or_none():
    res = sweep_snow(SCENARIO)
    for v in res.values():
        assert v is None or isinstance(v, float)


# ---------------------------------------------------------------- break at 0

def test_origin_broken_at_zero_inches_records_zero():
    # Any origin that run_simulation reports broken on a clear day (snow 0) at
    # the sweep hour must have first-break level 0 -- it was never fine.
    hour = SCENARIO["start_hour"] + SCENARIO["duration_hours"]
    clear = dict(SCENARIO)
    clear["snow_inches"] = 0
    sim0 = run_simulation(clear, hour)
    broken_at_zero = {o["node"] for o in sim0["origins"] if o["broken"]}

    res = sweep_snow(SCENARIO)
    for node in broken_at_zero:
        assert res[node] == 0.0


def test_origins_fine_at_zero_are_not_recorded_zero():
    hour = SCENARIO["start_hour"] + SCENARIO["duration_hours"]
    clear = dict(SCENARIO)
    clear["snow_inches"] = 0
    sim0 = run_simulation(clear, hour)
    fine_at_zero = {o["node"] for o in sim0["origins"] if not o["broken"]}

    res = sweep_snow(SCENARIO)
    for node in fine_at_zero:
        assert res[node] != 0.0  # either None or some positive level


# ---------------------------------------------------------------- monotonicity

def test_once_broken_stays_broken_so_first_break_is_well_defined():
    """For a sample of levels, confirm the brokenness is monotone in snow and
    that the recorded first-break level is exactly the lowest level at which
    run_simulation reports the origin broken (Requirement 15.4)."""
    hour = SCENARIO["start_hour"] + SCENARIO["duration_hours"]
    levels = _expected_levels()

    # Broken set per level straight from run_simulation (the source of truth).
    broken_by_level: dict[int, set[int]] = {}
    for level in levels:
        sc = dict(SCENARIO)
        sc["snow_inches"] = level
        sim = run_simulation(sc, hour)
        broken_by_level[level] = {o["node"] for o in sim["origins"] if o["broken"]}

    # Monotonicity: broken set never shrinks as snow rises.
    for lo, hi in zip(levels, levels[1:]):
        assert broken_by_level[lo] <= broken_by_level[hi], (
            f"an origin recovered between {lo} and {hi} inches"
        )

    # The sweep's first-break level equals the first level a node is broken.
    res = sweep_snow(SCENARIO, hour=hour)
    for node, recorded in res.items():
        first = next((lv for lv in levels if node in broken_by_level[lv]), None)
        expected = None if first is None else float(first)
        assert recorded == expected, f"node {node}: recorded {recorded}, expected {expected}"


def test_recorded_level_actually_breaks_and_prior_level_does_not():
    """Spot-check the definition directly: at the recorded first-break level the
    origin is broken; at the level just below it is not (Requirement 15.4)."""
    hour = SCENARIO["start_hour"] + SCENARIO["duration_hours"]
    res = sweep_snow(SCENARIO, hour=hour)

    # Pick a few origins that break at a positive level (not 0, not never).
    sample = [n for n, v in res.items() if v not in (None, 0.0)][:5]
    assert sample, "expected some origins to break at a positive snowfall"

    for node in sample:
        level = int(res[node])
        sc_at = dict(SCENARIO); sc_at["snow_inches"] = level
        broken_here = {o["node"] for o in run_simulation(sc_at, hour)["origins"]
                       if o["broken"]}
        assert node in broken_here

        prev = level - SWEEP_STEP_IN
        sc_prev = dict(SCENARIO); sc_prev["snow_inches"] = prev
        broken_prev = {o["node"] for o in run_simulation(sc_prev, hour)["origins"]
                       if o["broken"]}
        assert node not in broken_prev


# ---------------------------------------------------------------- ordering / robustness

def test_more_snow_breaks_at_least_as_many_origins():
    # Count of origins that have broken by level L is non-decreasing in L: it's
    # the count of first-break values <= L. Verify a low vs a high level.
    res = sweep_snow(SCENARIO)

    def broken_by(level: int) -> int:
        return sum(1 for v in res.values() if v is not None and v <= level)

    assert broken_by(4) <= broken_by(12) <= broken_by(SWEEP_MAX_IN)


def test_a_robust_origin_breaks_late_or_never_vs_fragile_one():
    """Ordering sanity: there exist origins that break early (low level) and
    origins that break late or never, and an early-breaking origin's level is
    <= a late/never one's. Picks the global min and max finite break levels."""
    res = sweep_snow(SCENARIO)
    finite = [v for v in res.values() if v is not None]
    assert finite, "expected at least one origin to break within 0..30 in"

    earliest = min(finite)
    latest = max(finite)
    assert earliest <= latest

    # Some origins should survive the whole range or break only near the top:
    # i.e. robust origins exist (None) OR the spread of break levels is real.
    never = [v for v in res.values() if v is None]
    assert never or earliest < latest, (
        "expected a spread between fragile and robust origins"
    )


def test_hour_defaults_to_end_of_storm():
    # Passing hour explicitly as start+duration must match the default.
    end = SCENARIO["start_hour"] + SCENARIO["duration_hours"]
    default = sweep_snow(SCENARIO)
    explicit = sweep_snow(SCENARIO, hour=end)
    assert default == explicit


def test_broken_definition_matches_threshold():
    # The sweep's brokenness uses the same > BROKEN_MINUTES / unreachable rule
    # as run_simulation: at the max snow level, every recorded break is backed
    # by run_simulation reporting broken there.
    hour = SCENARIO["start_hour"] + SCENARIO["duration_hours"]
    res = sweep_snow(SCENARIO, hour=hour)

    sc_max = dict(SCENARIO); sc_max["snow_inches"] = SWEEP_MAX_IN
    sim = run_simulation(sc_max, hour)
    broken_at_max = {o["node"] for o in sim["origins"] if o["broken"]}
    minutes = {o["node"]: o["minutes_to_hospital"] for o in sim["origins"]}

    # Every origin with a recorded (non-None) break level is broken at max snow.
    for node, v in res.items():
        if v is not None:
            assert node in broken_at_max
    # And every origin broken at max either exceeds the threshold or is unreachable.
    for node in broken_at_max:
        m = minutes[node]
        assert (not math.isfinite(m)) or m > BROKEN_MINUTES
