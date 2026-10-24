"""Authoritative origin-level monotonicity property test (task 6.4). Owner: B.

This is the top-level guarantee behind Requirement 3.6, stated in
.kiro/steering/simulation-assumptions.md as:

    "More snow never makes any edge faster or any origin closer."
    "Higher parking compliance never makes things worse."

The edge-level test in ``test_travel.py`` isolates the snow->capacity channel
with v/c held fixed. THIS test exercises the real ``run_simulation`` end to end
(all origins, one reversed multi-source Dijkstra) and asserts the contract at
the level people actually read: a per-origin ``minutes_to_hospital``.

Property (Requirement 3.6, extended to origin->hospital minutes):
  For a fixed hour and an otherwise-identical scenario,
    * increasing ``snow_inches`` never DECREASES any origin's minutes, and
    * decreasing ``parking_compliance`` never DECREASES any origin's minutes.
  ``inf`` (unreachable) is treated as the maximum, so an origin may become
  unreachable as conditions worsen; it may never become reachable-faster.

Validates: Requirements 3.6
"""
from __future__ import annotations

import math

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.contract import Scenario
from src.sim.simulate import _get_graph, run_simulation


def make_scenario(snow_inches: float, parking_compliance: float,
                  green_e_suspended: bool = False, start_hour: int = 0,
                  duration_hours: int = 20) -> Scenario:
    return {
        "snow_inches": snow_inches,
        "start_hour": start_hour,
        "duration_hours": duration_hours,
        "parking_compliance": parking_compliance,
        "green_e_suspended": green_e_suspended,
        "elevators_out": [],
    }


def _minutes_by_node(result) -> dict[int, float]:
    """node -> minutes_to_hospital (inf if unreachable) for every origin."""
    return {o["node"]: o["minutes_to_hospital"] for o in result["origins"]}


def _assert_no_origin_got_closer(worse, better, *, context: str) -> None:
    """Assert the WORSE scenario leaves every origin no closer than BETTER.

    ``inf`` is the maximum (unreachable), so becoming unreachable is allowed;
    becoming reachable-faster is the violation we forbid. A tiny tolerance
    absorbs floating-point noise in the shortest-path sums.
    """
    worse_min = _minutes_by_node(worse)
    better_min = _minutes_by_node(better)
    for node, better_minutes in better_min.items():
        worse_minutes = worse_min[node]
        if math.isinf(worse_minutes):
            # unreachable is the max; cannot be "closer" than anything.
            continue
        assert worse_minutes >= better_minutes - 1e-6, (
            f"{context}: origin {node} got CLOSER under the worse scenario "
            f"({worse_minutes:.6f} min) than the better one "
            f"({better_minutes:.6f} min)"
        )


# ---------------------------------------------------------------- example cases

def test_more_snow_never_speeds_up_the_whole_network():
    """A heavier storm never makes the average hospital trip faster (sanity)."""
    light = run_simulation(make_scenario(4.0, 0.6), hour=8)
    heavy = run_simulation(make_scenario(16.0, 0.6), hour=8)
    _assert_no_origin_got_closer(heavy, light, context="example: more snow")
    # KPI-level sanity: more origins (or the same) break under the heavier storm.
    assert heavy["kpis"]["pct_broken"] >= light["kpis"]["pct_broken"] - 1e-9


def test_lower_compliance_never_speeds_up_the_whole_network():
    """Fewer cars moved off priority routes never makes any origin closer."""
    good = run_simulation(make_scenario(10.0, 1.0), hour=8)
    bad = run_simulation(make_scenario(10.0, 0.0), hour=8)
    _assert_no_origin_got_closer(bad, good, context="example: lower compliance")


# ---------------------------------------------------------------- property tests

# One run_simulation covers all ~609 origins, so each example is a full solve.
# A bounded snow range and a modest example count keep the suite fast while
# still probing the plow-reset hours where the demand-drop interaction bit.
_SETTINGS = settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


@_SETTINGS
@given(
    snow=st.floats(min_value=0.0, max_value=18.0),
    extra=st.floats(min_value=0.0, max_value=12.0),
    compliance=st.floats(min_value=0.0, max_value=1.0),
    green_e_suspended=st.booleans(),
    hour=st.integers(min_value=0, max_value=19),
)
def test_more_snow_never_makes_any_origin_closer(snow, extra, compliance,
                                                 green_e_suspended, hour):
    """More snow, everything else fixed, never lowers any origin's minutes (Req 3.6)."""
    _get_graph()  # memoized once per process; keeps each example cheap
    less = make_scenario(snow, compliance, green_e_suspended)
    more = make_scenario(snow + extra, compliance, green_e_suspended)
    _assert_no_origin_got_closer(
        run_simulation(more, hour), run_simulation(less, hour),
        context=f"snow {snow}->{snow + extra} hour {hour} comp {compliance}",
    )


@_SETTINGS
@given(
    snow=st.floats(min_value=0.0, max_value=18.0),
    compliance=st.floats(min_value=0.0, max_value=1.0),
    drop=st.floats(min_value=0.0, max_value=1.0),
    green_e_suspended=st.booleans(),
    hour=st.integers(min_value=0, max_value=19),
)
def test_lower_compliance_never_makes_any_origin_closer(snow, compliance, drop,
                                                        green_e_suspended, hour):
    """Lower parking compliance, everything else fixed, never lowers any origin's minutes (Req 3.6)."""
    _get_graph()  # memoized once per process
    higher = min(1.0, compliance + drop)
    better = make_scenario(snow, higher, green_e_suspended)
    worse = make_scenario(snow, compliance, green_e_suspended)
    _assert_no_origin_got_closer(
        run_simulation(worse, hour), run_simulation(better, hour),
        context=f"compliance {higher}->{compliance} snow {snow} hour {hour}",
    )
