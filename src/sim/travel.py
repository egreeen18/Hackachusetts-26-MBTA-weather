"""Congested storm travel time for a single road edge (task 6.2).

Pure functions, no I/O. Rules mirror .kiro/steering/simulation-assumptions.md
(rule 5) and read every number from config/params.py. Builds on snow.py
(snow_on_road / capacity_factor, tasks 2.1-2.2) and capacity.py (parked cars
and v/c, task 6.1), and feeds the multi-source Dijkstra in run_simulation
(task 6.3) via an edge's ``sim_time``.

Rule 5 (Requirement 3.4):

    t = free_flow / capacity_factor ** SPEED_EXPONENT
          * (1 + BPR_ALPHA * min(v/c, VC_CAP) ** BPR_BETA)

where ``capacity_factor`` already folds in snow and parked-car losses. An
impassable edge (capacity factor 0 -- e.g. a side street with >= 12 in of snow)
gets an infinite travel time, which removes it from routing.
"""
from __future__ import annotations

import math

from config.params import (
    BPR_ALPHA,
    BPR_BETA,
    SPEED_EXPONENT,
    VC_CAP,
)
from src.contract import Scenario
from src.sim.capacity import (
    apply_parked_capacity,
    edge_vc,
    effective_snow_with_parking,
    is_huntington_edge,  # re-exported for callers assembling edge inputs
)
from src.sim.snow import capacity_factor, snow_on_road

__all__ = [
    "bpr",
    "edge_travel_time",
    "effective_capacity_factor",
    "is_huntington_edge",
]


def bpr(vc: float) -> float:
    """BPR congestion multiplier for a volume/capacity ratio (rule 5).

    ``1 + BPR_ALPHA * min(vc, VC_CAP) ** BPR_BETA``. The v/c is capped at
    ``VC_CAP`` so blizzard-era ratios stay plausible, and negative inputs are
    clamped to 0. Returns exactly 1.0 when there is no traffic (vc <= 0).
    """
    capped = min(max(0.0, float(vc)), VC_CAP)
    return 1.0 + BPR_ALPHA * capped ** BPR_BETA


def edge_travel_time(free_flow_s: float, cap: float, vc: float) -> float:
    """Congested storm travel time (seconds) for one edge (rule 5, Req 3.4).

    ``free_flow_s``  free-flow travel time in seconds (from the drive graph).
    ``cap``          effective capacity factor in [0, 1] after snow + parked
                     cars (see :func:`effective_capacity_factor`).
    ``vc``           volume/capacity ratio for the edge (see ``capacity.edge_vc``).

    When ``cap`` is 0 the edge is impassable, so the travel time is +inf and the
    edge drops out of any shortest-path search (Requirement 3.4). Snow lowers
    ``cap`` toward 0, which raises the travel time, so time is monotonic in snow.
    """
    if cap <= 0.0:
        return math.inf
    speed_factor = cap ** SPEED_EXPONENT          # snow slows free-flow speed
    return (free_flow_s / speed_factor) * bpr(vc)


def effective_capacity_factor(road_class: str, road_name, scenario: Scenario,
                              hour: int) -> float:
    """Effective capacity factor for an edge from snow + parked cars (rule 3-5).

    Composes the pieces B already built, consistent with task 6.1's model of
    parked cars blocking plows on priority routes:

      1. snow that fell since the last plow (``snow_on_road``);
      2. on a priority route, add the share of the pre-plow snow that parked
         cars keep behind (``effective_snow_with_parking``);
      3. turn that snow into a snow-only capacity factor (``capacity_factor``,
         which also closes side streets at >= 12 in);
      4. apply the parked-car capacity loss on priority routes
         (``apply_parked_capacity``).

    ``road_name`` is the edge's OSM name (string or list); it is unused here but
    kept in the signature so callers can pass the same edge attributes they give
    to ``capacity.edge_vc``. The result stays in [0, 1]; 0 means impassable.
    """
    cleared = snow_on_road(road_class, scenario, hour)
    # Snow present just before the last plow pass -- what a parked car can trap.
    # One plow interval's worth of accumulation is the snow that was cleared,
    # approximated by the snow that would sit on an unplowed road (side class)
    # since the storm start is handled inside snow_on_road; here we reuse the
    # cleared amount as the residual a plow would have removed.
    residual = cleared
    snow_in = effective_snow_with_parking(cleared, residual, road_class, scenario)
    base = capacity_factor(snow_in, road_class)
    return apply_parked_capacity(base, road_class, scenario)


def edge_sim_time(free_flow_s: float, road_class: str, road_name,
                  scenario: Scenario, hour: int) -> float:
    """End-to-end congested travel time for an edge from its attributes.

    Convenience combiner for task 6.3: assembles the effective capacity factor
    and the v/c, then applies rule 5. ``road_name`` drives both the Huntington
    E-suspension bump (via ``edge_vc``) and is accepted by
    ``effective_capacity_factor`` for symmetry.
    """
    cap = effective_capacity_factor(road_class, road_name, scenario, hour)
    vc = edge_vc(road_class, road_name, scenario, hour)
    return edge_travel_time(free_flow_s, cap, vc)
