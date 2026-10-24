"""Trip-level monotonicity property test for ``trip_time`` (task 16). Owner: B.

Requirement 3.6 says worsening conditions never make any road segment faster;
task 6.4 already proves that at the origin->hospital level through
``run_simulation``. THIS test proves the same guarantee holds for a single
point-to-point ``trip_time`` call, which is what the "My trip" tab and the
"leave earlier" number depend on (Requirement 16.3).

Property (Requirement 3.6, applied to one trip's storm minutes):
  For a FIXED origin, destination and hour, with everything else held equal,
    * increasing ``snow_inches`` never DECREASES the storm ``minutes``, and
    * decreasing ``parking_compliance`` never DECREASES the storm ``minutes``.
  ``inf`` (the trip became unroutable) is treated as the maximum, so a trip may
  break as the storm worsens but may never come back faster.

We route between two of the three hospital coordinates, which are a short,
clearly routable drive apart on a clear day, and reuse the memoized drive graph
so each example is just two shortest-path solves.

Validates: Requirements 3.6, 16.3
"""
from __future__ import annotations

import math

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.contract import Scenario, trip_time
from src.sim.simulate import _get_graph

# Two hospital coordinates a short drive apart; routable on a clear day.
BIDMC = (42.33979095, -71.10515721024117)       # Beth Israel East Campus
CHILDRENS = (42.33717145, -71.10567907164955)   # Boston Children's


def make_scenario(snow_inches: float, parking_compliance: float,
                  green_e_suspended: bool = False, start_hour: int = 7,
                  duration_hours: int = 10) -> Scenario:
    return {
        "snow_inches": snow_inches,
        "start_hour": start_hour,
        "duration_hours": duration_hours,
        "parking_compliance": parking_compliance,
        "green_e_suspended": green_e_suspended,
        "elevators_out": [],
    }


def _assert_not_faster(worse_minutes: float, better_minutes: float, *,
                       context: str) -> None:
    """Assert the WORSE scenario's trip is no faster than the BETTER one.

    ``inf`` is the maximum (unroutable), so becoming unroutable is allowed;
    becoming routable-faster is the violation. A tiny tolerance absorbs
    floating-point noise in the shortest-path sums.
    """
    if math.isinf(worse_minutes):
        return  # unroutable is the slowest possible outcome
    assert worse_minutes >= better_minutes - 1e-6, (
        f"{context}: trip got FASTER under the worse scenario "
        f"({worse_minutes:.6f} min) than the better one "
        f"({better_minutes:.6f} min)"
    )


# ---------------------------------------------------------------- example cases

def test_more_snow_never_makes_the_trip_faster_example():
    light = trip_time(BIDMC, CHILDRENS, make_scenario(4.0, 0.6), hour=10)
    heavy = trip_time(BIDMC, CHILDRENS, make_scenario(16.0, 0.6), hour=10)
    _assert_not_faster(heavy["minutes"], light["minutes"],
                       context="example: more snow")


def test_lower_compliance_never_makes_the_trip_faster_example():
    good = trip_time(BIDMC, CHILDRENS, make_scenario(10.0, 1.0), hour=10)
    bad = trip_time(BIDMC, CHILDRENS, make_scenario(10.0, 0.0), hour=10)
    _assert_not_faster(bad["minutes"], good["minutes"],
                       context="example: lower compliance")


# ---------------------------------------------------------------- property tests

# Each example is two point-to-point Dijkstra solves on the memoized graph, so a
# modest example count with a bounded snow range keeps the suite fast while
# still probing plow-reset hours across the storm.
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
def test_more_snow_never_makes_the_trip_faster(snow, extra, compliance,
                                               green_e_suspended, hour):
    """More snow, everything else fixed, never lowers the trip's storm minutes."""
    _get_graph()  # memoized once per process; keeps each example cheap
    less = trip_time(BIDMC, CHILDRENS,
                     make_scenario(snow, compliance, green_e_suspended), hour)
    more = trip_time(BIDMC, CHILDRENS,
                     make_scenario(snow + extra, compliance, green_e_suspended),
                     hour)
    _assert_not_faster(
        more["minutes"], less["minutes"],
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
def test_lower_compliance_never_makes_the_trip_faster(snow, compliance, drop,
                                                      green_e_suspended, hour):
    """Lower parking compliance, everything else fixed, never lowers storm minutes."""
    _get_graph()  # memoized once per process
    higher = min(1.0, compliance + drop)
    better = trip_time(BIDMC, CHILDRENS,
                       make_scenario(snow, higher, green_e_suspended), hour)
    worse = trip_time(BIDMC, CHILDRENS,
                      make_scenario(snow, compliance, green_e_suspended), hour)
    _assert_not_faster(
        worse["minutes"], better["minutes"],
        context=f"compliance {higher}->{compliance} snow {snow} hour {hour}",
    )
