"""Snow accumulation on a road and the resulting capacity factor.

Pure functions, no I/O. Rules mirror .kiro/steering/simulation-assumptions.md
and read every number from config/params.py.

Task 2.1: snow_on_road(road_class, scenario, hour)
Task 2.2: capacity_factor(snow_in, road_class)
"""
from __future__ import annotations

from config.params import (
    CAPACITY_TABLE,
    PLOW_INTERVAL_H,
    SIDE_STREET_IMPASSABLE_IN,
    SIDE_STREET_PLOW_DELAY_H,
)
from src.contract import Scenario


def _snowfall_rate(scenario: Scenario) -> float:
    """Inches of snow per hour, spread evenly over the storm (rule 1)."""
    total = float(scenario.get("snow_inches", 0.0))
    duration = int(scenario.get("duration_hours", 0) or 0)
    if total <= 0 or duration <= 0:
        return 0.0
    return total / duration


def _inches_fallen_between(scenario: Scenario, h0: float, h1: float) -> float:
    """Snow that fell in the clock-hour window [h0, h1], clipped to the storm."""
    if h1 <= h0:
        return 0.0
    rate = _snowfall_rate(scenario)
    if rate == 0.0:
        return 0.0
    start = float(scenario.get("start_hour", 0))
    end = start + int(scenario.get("duration_hours", 0) or 0)
    lo = max(h0, start)
    hi = min(h1, end)
    if hi <= lo:
        return 0.0
    return rate * (hi - lo)


def _last_plow_hour(road_class: str, scenario: Scenario, hour: float) -> float:
    """Clock hour of the most recent plow pass at or before `hour`.

    Priority/main roads are plowed on a fixed interval starting at the storm
    start. Side streets are not plowed during the storm; they are cleared
    SIDE_STREET_PLOW_DELAY_H after the snow stops (rule 2).
    """
    start = float(scenario.get("start_hour", 0))
    interval = PLOW_INTERVAL_H.get(road_class)

    if interval is None:
        # Side streets: only cleared after the storm ends.
        end = start + int(scenario.get("duration_hours", 0) or 0)
        cleared_at = end + SIDE_STREET_PLOW_DELAY_H
        return cleared_at if hour >= cleared_at else start

    if hour < start:
        return hour  # before the storm there is no snow anyway
    passes = int((hour - start) // interval)
    return start + passes * interval


def snow_on_road(road_class: str, scenario: Scenario, hour: int) -> float:
    """Inches of snow built up on a road of `road_class` at clock `hour`.

    Snow accumulates evenly over the storm; a plow pass resets accumulation,
    so what matters is snow that fell since the last plow (rules 1-2).
    """
    last_plow = _last_plow_hour(road_class, scenario, hour)
    return _inches_fallen_between(scenario, last_plow, float(hour))


def capacity_factor(snow_in: float, road_class: str) -> float:
    """Road capacity multiplier from snow on the road (rule 4).

    0.0 = impassable, 1.0 = normal. Linear interpolation of CAPACITY_TABLE.
    Side streets with SIDE_STREET_IMPASSABLE_IN or more inches are closed.
    """
    if road_class == "side" and snow_in >= SIDE_STREET_IMPASSABLE_IN:
        return 0.0

    snow_in = max(0.0, snow_in)
    points = CAPACITY_TABLE  # sorted ascending by inches

    # Clamp to the ends of the table.
    if snow_in <= points[0][0]:
        return points[0][1]
    if snow_in >= points[-1][0]:
        return points[-1][1]

    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= snow_in <= x1:
            span = x1 - x0
            if span == 0:
                return y1
            t = (snow_in - x0) / span
            return y0 + t * (y1 - y0)

    return points[-1][1]
