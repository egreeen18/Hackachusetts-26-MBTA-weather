"""Tests for src/sim/snow.py (task 2.3).

Covers the example cases plus the property-test guarantees listed in
.kiro/steering/simulation-assumptions.md:
  - more snow never lowers snow-on-road
  - 0 inches of snow gives capacity factor 1.0
  - more snow never raises the capacity factor
  - while snow is falling, priority routes never hold more snow than side
    streets at the same hour
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from config.params import SIDE_STREET_IMPASSABLE_IN, SIDE_STREET_PLOW_DELAY_H
from src.contract import Scenario
from src.sim.snow import capacity_factor, snow_on_road


def make_scenario(snow_inches: float, start_hour: int = 7,
                  duration_hours: int = 10) -> Scenario:
    return {
        "snow_inches": snow_inches,
        "start_hour": start_hour,
        "duration_hours": duration_hours,
        "parking_compliance": 0.6,
        "green_e_suspended": False,
        "elevators_out": [],
    }


# ---------------------------------------------------------------- capacity_factor

def test_zero_snow_is_full_capacity():
    for rc in ("priority", "main", "side"):
        assert capacity_factor(0.0, rc) == 1.0


def test_capacity_table_anchor_points():
    assert capacity_factor(2, "main") == 0.7
    assert capacity_factor(4, "main") == 0.5
    assert capacity_factor(8, "main") == 0.3


def test_capacity_interpolates_between_points():
    # halfway between 0in(1.0) and 2in(0.7) -> 0.85
    assert capacity_factor(1, "main") == 0.85


def test_side_street_impassable_above_threshold():
    assert capacity_factor(SIDE_STREET_IMPASSABLE_IN, "side") == 0.0
    assert capacity_factor(SIDE_STREET_IMPASSABLE_IN + 5, "side") == 0.0
    # a main road with the same snow is NOT auto-closed
    assert capacity_factor(SIDE_STREET_IMPASSABLE_IN, "main") > 0.0


# ---------------------------------------------------------------- snow_on_road

def test_no_snow_before_storm_starts():
    sc = make_scenario(14, start_hour=7, duration_hours=10)
    assert snow_on_road("priority", sc, 6) == 0.0


def test_priority_is_plowed_more_often_so_holds_less():
    sc = make_scenario(20, start_hour=0, duration_hours=20)
    hour = 12
    assert snow_on_road("priority", sc, hour) < snow_on_road("side", sc, hour)


def test_zero_snow_means_no_snow_on_road_at_every_hour():
    sc = make_scenario(0, start_hour=7, duration_hours=10)
    for rc in ("priority", "main", "side"):
        for hour in range(0, 24):
            assert snow_on_road(rc, sc, hour) == 0.0


def test_even_accumulation_mid_storm_on_side_streets():
    # 20 in over 20 h = 1 in/h. Side streets are not plowed during the storm,
    # so by hour 12 (12 h of falling snow) they hold ~12 in.
    sc = make_scenario(20, start_hour=0, duration_hours=20)
    assert snow_on_road("side", sc, 12) == 12.0
    assert snow_on_road("side", sc, 5) == 5.0


def test_priority_plow_resets_every_two_hours():
    # 20 in over 20 h = 1 in/h, priority plowed every 2 h starting at hour 0.
    # At an odd hour one hour of snow has fallen since the last even-hour plow.
    sc = make_scenario(20, start_hour=0, duration_hours=20)
    assert snow_on_road("priority", sc, 1) == 1.0   # 1 h since plow at hour 0
    assert snow_on_road("priority", sc, 3) == 1.0   # 1 h since plow at hour 2
    assert snow_on_road("priority", sc, 9) == 1.0   # 1 h since plow at hour 8
    # Snow-on-road for priority never exceeds the 2-hour interval's accumulation.
    for hour in range(0, 20):
        assert snow_on_road("priority", sc, hour) <= 2.0 + 1e-9


def test_main_plow_resets_every_four_hours():
    # 20 in over 20 h = 1 in/h, main roads plowed every 4 h starting at hour 0.
    sc = make_scenario(20, start_hour=0, duration_hours=20)
    assert snow_on_road("main", sc, 3) == 3.0   # 3 h since plow at hour 0
    assert snow_on_road("main", sc, 7) == 3.0   # 3 h since plow at hour 4
    # Never exceeds the 4-hour interval's accumulation.
    for hour in range(0, 20):
        assert snow_on_road("main", sc, hour) <= 4.0 + 1e-9


def test_side_street_cleared_after_storm_ends():
    # Storm: 20 in over hours 0..20. Side streets peak at the storm's end
    # (full 20 in) and are cleared SIDE_STREET_PLOW_DELAY_H hours later.
    sc = make_scenario(20, start_hour=0, duration_hours=20)
    end = 20
    # At the end of the storm the side street holds all the snow.
    assert snow_on_road("side", sc, end) == 20.0
    # Still snowbound during the post-storm clearing delay.
    assert snow_on_road("side", sc, end + SIDE_STREET_PLOW_DELAY_H - 1) == 20.0
    # Cleared once the delay has elapsed.
    assert snow_on_road("side", sc, end + SIDE_STREET_PLOW_DELAY_H) == 0.0
    assert snow_on_road("side", sc, end + SIDE_STREET_PLOW_DELAY_H + 5) == 0.0


# ---------------------------------------------------------------- property tests

@settings(max_examples=200)
@given(
    snow=st.floats(min_value=0, max_value=60),
    road_class=st.sampled_from(["priority", "main", "side"]),
)
def test_more_snow_never_raises_capacity(snow, road_class):
    assert capacity_factor(snow + 1.0, road_class) <= capacity_factor(snow, road_class) + 1e-9


@settings(max_examples=200)
@given(
    base=st.floats(min_value=0, max_value=40),
    extra=st.floats(min_value=0, max_value=20),
    road_class=st.sampled_from(["priority", "main", "side"]),
    hour=st.integers(min_value=0, max_value=47),
)
def test_more_snowfall_never_lowers_snow_on_road(base, extra, road_class, hour):
    low = make_scenario(base, start_hour=0, duration_hours=20)
    high = make_scenario(base + extra, start_hour=0, duration_hours=20)
    assert snow_on_road(road_class, high, hour) >= snow_on_road(road_class, low, hour) - 1e-9


@settings(max_examples=200)
@given(
    road_class=st.sampled_from(["priority", "main", "side"]),
    start_hour=st.integers(min_value=0, max_value=23),
    duration_hours=st.integers(min_value=1, max_value=24),
    hour=st.integers(min_value=0, max_value=47),
)
def test_zero_snowfall_is_always_zero_on_road(road_class, start_hour,
                                              duration_hours, hour):
    sc = make_scenario(0, start_hour=start_hour, duration_hours=duration_hours)
    assert snow_on_road(road_class, sc, hour) == 0.0


@settings(max_examples=200)
@given(
    snow=st.floats(min_value=1, max_value=40),
    hour=st.integers(min_value=0, max_value=19),
)
def test_priority_never_snowier_than_side_during_storm(snow, hour):
    # storm runs hours 0..20, so hour 0..19 is "while snow is falling"
    sc = make_scenario(snow, start_hour=0, duration_hours=20)
    assert snow_on_road("priority", sc, hour) <= snow_on_road("side", sc, hour) + 1e-9
