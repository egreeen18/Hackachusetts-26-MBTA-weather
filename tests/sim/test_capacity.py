"""Tests for src/sim/capacity.py (task 6.1).

Covers the example cases plus property-test guarantees from
.kiro/steering/simulation-assumptions.md (rules 3, 6, 7):
  - parked-car loss is 0 at full compliance and PARKED_CAPACITY_LOSS at 0
  - volume drops with snow, capped at 0.5
  - E-suspension adds extra v/c only on Huntington edges and only when suspended
  - rush/day/night bucketing is correct

Validates: Requirements 3.3, 3.5
"""
from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from config.params import (
    BASE_VC,
    DEMAND_DROP_PER_INCH,
    E_SUSPENSION_EXTRA_VC,
    NIGHT_HOURS,
    PARKED_CAPACITY_LOSS,
    PARKED_PLOW_BLOCK,
    RUSH_HOURS,
)
from src.contract import Scenario
from src.sim.capacity import (
    apply_parked_capacity,
    base_vc,
    demand_drop_factor,
    e_suspension_extra_vc,
    edge_vc,
    effective_snow_with_parking,
    is_huntington_edge,
    parked_capacity_multiplier,
    parked_plow_block_fraction,
    time_of_day_bucket,
    volume_vc,
)


def make_scenario(snow_inches: float = 14, start_hour: int = 7,
                  duration_hours: int = 10, parking_compliance: float = 0.6,
                  green_e_suspended: bool = False) -> Scenario:
    return {
        "snow_inches": snow_inches,
        "start_hour": start_hour,
        "duration_hours": duration_hours,
        "parking_compliance": parking_compliance,
        "green_e_suspended": green_e_suspended,
        "elevators_out": [],
    }


# ----------------------------------------------------- parked cars (Req 3.3)

def test_parked_loss_zero_at_full_compliance():
    sc = make_scenario(parking_compliance=1.0)
    assert parked_capacity_multiplier("priority", sc) == 1.0
    assert apply_parked_capacity(0.8, "priority", sc) == 0.8


def test_parked_loss_is_full_at_zero_compliance():
    sc = make_scenario(parking_compliance=0.0)
    assert parked_capacity_multiplier("priority", sc) == 1.0 - PARKED_CAPACITY_LOSS
    # a base capacity of 1.0 drops by exactly PARKED_CAPACITY_LOSS
    assert apply_parked_capacity(1.0, "priority", sc) == 1.0 - PARKED_CAPACITY_LOSS


def test_parked_loss_only_on_priority_routes():
    sc = make_scenario(parking_compliance=0.0)
    for rc in ("main", "side"):
        assert parked_capacity_multiplier(rc, sc) == 1.0
        assert apply_parked_capacity(0.7, rc, sc) == 0.7


def test_parked_plow_block_fraction():
    # 0 compliance -> full PARKED_PLOW_BLOCK stays on priority routes
    assert parked_plow_block_fraction("priority", make_scenario(parking_compliance=0.0)) == PARKED_PLOW_BLOCK
    # full compliance -> nothing stays
    assert parked_plow_block_fraction("priority", make_scenario(parking_compliance=1.0)) == 0.0
    # non-priority roads block nothing regardless
    assert parked_plow_block_fraction("main", make_scenario(parking_compliance=0.0)) == 0.0


def test_effective_snow_with_parking_adds_residual_on_priority():
    sc = make_scenario(parking_compliance=0.0)  # half the residual snow stays
    # cleared=1 (fell since plow) + 0.5 * residual(4) = 1 + 2 = 3
    assert effective_snow_with_parking(1.0, 4.0, "priority", sc) == 3.0
    # on a side street nothing is blocked -> only the cleared snow
    assert effective_snow_with_parking(1.0, 4.0, "side", sc) == 1.0


# ----------------------------------------------------- volume / demand (rule 6)

def test_rush_day_night_bucketing():
    for h in RUSH_HOURS:
        assert time_of_day_bucket(h) == "rush"
    for h in NIGHT_HOURS:
        assert time_of_day_bucket(h) == "night"
    # a known non-rush, non-night hour (noon) is "day"
    assert time_of_day_bucket(12) == "day"
    # every hour maps to exactly one known bucket
    for h in range(24):
        assert time_of_day_bucket(h) in ("rush", "day", "night")


def test_base_vc_reads_from_table():
    assert base_vc("priority", 8) == BASE_VC["rush"]["priority"]   # 8 is rush
    assert base_vc("main", 12) == BASE_VC["day"]["main"]           # noon is day
    assert base_vc("side", 2) == BASE_VC["night"]["side"]          # 2am is night


def test_demand_drop_no_snow_is_no_drop():
    assert demand_drop_factor(make_scenario(snow_inches=0)) == 1.0


def test_demand_drop_increases_with_snow():
    low = demand_drop_factor(make_scenario(snow_inches=5))
    high = demand_drop_factor(make_scenario(snow_inches=10))
    assert high < low < 1.0
    # 5 in -> 1 - 0.02*5 = 0.90
    assert math.isclose(low, 1.0 - DEMAND_DROP_PER_INCH * 5)


def test_demand_drop_capped_at_half():
    # 100 in would be a 2.0 drop uncapped; must cap at 0.5 -> factor 0.5
    assert demand_drop_factor(make_scenario(snow_inches=100)) == 0.5
    # exactly at the cap boundary: 25 in -> 0.02*25 = 0.5
    assert demand_drop_factor(make_scenario(snow_inches=25)) == 0.5


def test_volume_vc_applies_demand_drop():
    sc = make_scenario(snow_inches=10)  # factor 0.8
    assert math.isclose(volume_vc("priority", sc, 8), BASE_VC["rush"]["priority"] * 0.8)


# ----------------------------------------------------- E suspension (Req 3.5)

def test_e_suspension_adds_only_on_huntington_when_suspended():
    suspended = make_scenario(green_e_suspended=True)
    not_suspended = make_scenario(green_e_suspended=False)
    # Huntington + suspended -> extra
    assert e_suspension_extra_vc(True, suspended) == E_SUSPENSION_EXTRA_VC
    # Huntington but not suspended -> nothing
    assert e_suspension_extra_vc(True, not_suspended) == 0.0
    # not Huntington, suspended -> nothing
    assert e_suspension_extra_vc(False, suspended) == 0.0
    # not Huntington, not suspended -> nothing
    assert e_suspension_extra_vc(False, not_suspended) == 0.0


def test_is_huntington_edge_handles_string_and_list():
    assert is_huntington_edge("Huntington Avenue") is True
    assert is_huntington_edge(["Huntington Avenue", "MA-9"]) is True
    assert is_huntington_edge("Longwood Avenue") is False
    assert is_huntington_edge(["Boylston Street", "MA-9"]) is False
    assert is_huntington_edge(None) is False


def test_edge_vc_bumps_huntington_when_suspended():
    sc = make_scenario(snow_inches=0, green_e_suspended=True)
    base = volume_vc("priority", sc, 8)
    assert edge_vc("priority", "Huntington Avenue", sc, 8) == base + E_SUSPENSION_EXTRA_VC
    # a different priority route gets no bump
    assert edge_vc("priority", "Longwood Avenue", sc, 8) == base


# ----------------------------------------------------- property tests

@settings(max_examples=200)
@given(compliance=st.floats(min_value=0.0, max_value=1.0))
def test_higher_compliance_never_lowers_capacity(compliance):
    # monotonic: more compliance -> capacity multiplier at least as high
    lo = parked_capacity_multiplier("priority", make_scenario(parking_compliance=compliance))
    hi = parked_capacity_multiplier(
        "priority", make_scenario(parking_compliance=min(1.0, compliance + 0.1)))
    assert hi >= lo - 1e-9


@settings(max_examples=200)
@given(snow=st.floats(min_value=0, max_value=30), extra=st.floats(min_value=0, max_value=30))
def test_more_snow_never_raises_demand(snow, extra):
    lo = demand_drop_factor(make_scenario(snow_inches=snow))
    hi = demand_drop_factor(make_scenario(snow_inches=snow + extra))
    assert hi <= lo + 1e-9
    assert 0.5 <= hi <= 1.0


@settings(max_examples=200)
@given(
    is_hunt=st.booleans(),
    suspended=st.booleans(),
)
def test_e_extra_is_zero_or_the_constant(is_hunt, suspended):
    extra = e_suspension_extra_vc(is_hunt, make_scenario(green_e_suspended=suspended))
    expected = E_SUSPENSION_EXTRA_VC if (is_hunt and suspended) else 0.0
    assert extra == expected
