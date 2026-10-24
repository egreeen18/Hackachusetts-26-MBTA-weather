"""Interface contract for the Storm Twin simulator.

EVERYONE codes against these signatures. The UI (C), the demo scripts (D) and the
personal agent (later) call ONLY these functions. Person B replaces the fake bodies
with real ones; the return shapes must not change without telling the team.

The stub returns fake but correctly shaped data, so the UI can be built from 12:15
without waiting for the real simulator.
"""
from __future__ import annotations

import random
from typing import TypedDict


class Scenario(TypedDict, total=False):
    snow_inches: float          # total storm snowfall
    start_hour: int             # hour snow starts, 0-23
    duration_hours: int         # storm length; snow is spread evenly over it
    parking_compliance: float   # 0..1, share of cars moved off priority routes
    green_e_suspended: bool     # E branch down -> more cars on Huntington Ave
    elevators_out: list[str]    # MBTA stop ids (only used by trip_time, transit mode)


class EdgeResult(TypedDict):
    u: int
    v: int
    key: int
    capacity_factor: float      # 1.0 = normal, 0.0 = impassable
    travel_time_s: float        # inf if impassable
    snow_on_road_in: float      # snow built up since last plow


class OriginResult(TypedDict):
    node: int
    lat: float
    lon: float
    minutes_to_hospital: float  # inf if unreachable
    nearest_hospital: str | None
    broken: bool                # > BROKEN_MINUTES or unreachable


class KPIs(TypedDict):
    pct_broken: float
    avg_minutes_to_hospital: float   # over reachable origins only
    n_unreachable: int


class SimResult(TypedDict):
    hour: int
    edges: list[EdgeResult]
    origins: list[OriginResult]
    kpis: KPIs
    label: str                  # always "simulation estimate"


class TripResult(TypedDict):
    minutes: float              # inf if no route
    clear_day_minutes: float
    broken: bool
    leave_earlier_by_min: float # extra time vs a clear day
    route_nodes: list[int]
    warnings: list[str]         # e.g. "Elevator out at Longwood"


DEFAULT_SCENARIO: Scenario = {
    "snow_inches": 14,
    "start_hour": 7,
    "duration_hours": 10,
    "parking_compliance": 0.6,
    "green_e_suspended": False,
    "elevators_out": [],
}


# ---------------------------------------------------------------- stubs (B replaces)

def run_simulation(scenario: Scenario, hour: int) -> SimResult:
    rng = random.Random(int(scenario.get("snow_inches", 0) * 100 + hour))
    origins: list[OriginResult] = []
    for i in range(50):
        m = rng.uniform(5, 15) + scenario.get("snow_inches", 0) * rng.uniform(0.5, 2.5)
        origins.append({
            "node": i, "lat": 42.33 + rng.random() * 0.02, "lon": -71.115 + rng.random() * 0.03,
            "minutes_to_hospital": m, "nearest_hospital": "Brigham and Women's Hospital",
            "broken": m > 30,
        })
    broken = sum(o["broken"] for o in origins)
    return {
        "hour": hour,
        "edges": [],
        "origins": origins,
        "kpis": {
            "pct_broken": 100 * broken / len(origins),
            "avg_minutes_to_hospital": sum(o["minutes_to_hospital"] for o in origins) / len(origins),
            "n_unreachable": 0,
        },
        "label": "simulation estimate",
    }


def sweep_snow(scenario: Scenario, hour: int | None = None,
               max_inches: int = 30, step: int = 2) -> dict[int, float | None]:
    """node -> first snowfall (inches) at which that origin breaks; None = never breaks
    up to max_inches. `hour` defaults to start_hour + duration_hours (end of storm)."""
    return {i: random.Random(i).choice([None, 8, 12, 16, 20, 24]) for i in range(50)}


def trip_time(origin: tuple[float, float], dest: tuple[float, float],
              scenario: Scenario, hour: int) -> TripResult:
    return {"minutes": 28.0, "clear_day_minutes": 12.0, "broken": False,
            "leave_earlier_by_min": 16.0, "route_nodes": [], "warnings": []}
