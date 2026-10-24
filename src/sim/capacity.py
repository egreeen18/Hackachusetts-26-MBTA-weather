"""Capacity and volume adjustments on top of the snow model.

Pure functions, no I/O. Rules mirror .kiro/steering/simulation-assumptions.md
and read every number from config/params.py. These build on snow.py's
snow_on_road / capacity_factor (tasks 2.1-2.3) and feed edge travel times and
run_simulation (tasks 6.2-6.3).

Task 6.1 covers:
  - parked cars on priority routes (rule 3, Requirement 3.3)
  - baseline v/c by class and time of day, reduced by demand drop (rule 6)
  - Green Line E suspension extra v/c on Huntington Ave (rule 7, Requirement 3.5)
"""
from __future__ import annotations

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

# The priority route whose edges carry diverted E-branch traffic (rule 7).
HUNTINGTON_AVENUE = "Huntington Avenue"


def _compliance(scenario: Scenario) -> float:
    """Share of cars moved off priority routes, clamped to 0..1."""
    c = float(scenario.get("parking_compliance", 0.0) or 0.0)
    return min(1.0, max(0.0, c))


# ------------------------------------------------------------ parked cars (rule 3)

def parked_capacity_multiplier(road_class: str, scenario: Scenario) -> float:
    """Capacity multiplier from cars parked on priority routes (rule 3, Req 3.3).

    Priority routes only: ``1 - PARKED_CAPACITY_LOSS * (1 - compliance)``.
    Full compliance (1.0) leaves capacity untouched (1.0); zero compliance
    removes the full PARKED_CAPACITY_LOSS. Non-priority roads are unaffected.
    """
    if road_class != "priority":
        return 1.0
    compliance = _compliance(scenario)
    return 1.0 - PARKED_CAPACITY_LOSS * (1.0 - compliance)


def apply_parked_capacity(base_capacity: float, road_class: str,
                          scenario: Scenario) -> float:
    """Apply the parked-car loss to a base capacity factor on priority routes.

    ``base_capacity`` is the snow-only capacity factor from
    ``snow.capacity_factor``; the result keeps the [0, 1] range.
    """
    return base_capacity * parked_capacity_multiplier(road_class, scenario)


def parked_plow_block_fraction(road_class: str, scenario: Scenario) -> float:
    """Share of snow left behind by a plow pass where cars block it (rule 3).

    After a plow pass on a priority route, ``PARKED_PLOW_BLOCK * (1 - compliance)``
    of the snow stays. Non-priority roads block nothing. This is the hook that
    lets snow accumulation account for parked cars without changing snow.py's
    core plow model.
    """
    if road_class != "priority":
        return 0.0
    compliance = _compliance(scenario)
    return PARKED_PLOW_BLOCK * (1.0 - compliance)


def effective_snow_with_parking(cleared_snow: float, residual_snow: float,
                                road_class: str, scenario: Scenario) -> float:
    """Effective snow on a priority route given parked-car plow blocking (rule 3).

    ``cleared_snow`` is snow that fell since the last plow (what snow_on_road
    already returns); ``residual_snow`` is the snow present just before that
    plow pass, a share of which stays behind parked cars. On non-priority roads
    nothing is blocked, so only the newly fallen snow matters.
    """
    blocked = parked_plow_block_fraction(road_class, scenario) * max(0.0, residual_snow)
    return max(0.0, cleared_snow) + blocked


# ------------------------------------------------------------ volume / v/c (rule 6)

def time_of_day_bucket(hour: int) -> str:
    """Map a clock hour to a demand bucket: 'rush', 'night', or 'day' (rule 6)."""
    h = int(hour) % 24
    if h in RUSH_HOURS:
        return "rush"
    if h in NIGHT_HOURS:
        return "night"
    return "day"


def base_vc(road_class: str, hour: int) -> float:
    """Baseline v/c for a (road_class, hour) from BASE_VC buckets (rule 6)."""
    bucket = time_of_day_bucket(hour)
    return BASE_VC[bucket][road_class]


def demand_drop_factor(scenario: Scenario) -> float:
    """Volume multiplier from people staying home (rule 6).

    ``1 - min(0.5, DEMAND_DROP_PER_INCH * snow_inches)`` — more snow means less
    traffic, capped so at most half the baseline demand disappears.
    """
    snow_inches = max(0.0, float(scenario.get("snow_inches", 0.0) or 0.0))
    return 1.0 - min(0.5, DEMAND_DROP_PER_INCH * snow_inches)


def volume_vc(road_class: str, scenario: Scenario, hour: int) -> float:
    """Demand-adjusted baseline v/c for a (road_class, hour) (rule 6).

    This is the v/c before the E-suspension bump; snow-driven capacity loss is
    handled separately (it lowers ``c`` in the travel-time formula, task 6.2).
    """
    return base_vc(road_class, hour) * demand_drop_factor(scenario)


# ------------------------------------------------- E-branch suspension (rule 7)

def e_suspension_extra_vc(is_huntington: bool, scenario: Scenario) -> float:
    """Extra v/c added to Huntington Ave edges when the E branch is down (rule 7).

    Returns ``E_SUSPENSION_EXTRA_VC`` only when the edge is on Huntington Avenue
    and ``green_e_suspended`` is True; otherwise 0.0.
    """
    if is_huntington and bool(scenario.get("green_e_suspended", False)):
        return E_SUSPENSION_EXTRA_VC
    return 0.0


def is_huntington_edge(road_name) -> bool:
    """True if an edge's OSM name is Huntington Avenue.

    OSM ``name`` can be a string or a list of strings; match either shape.
    """
    if road_name is None:
        return False
    if isinstance(road_name, (list, tuple, set)):
        return any(is_huntington_edge(n) for n in road_name)
    return str(road_name) == HUNTINGTON_AVENUE


def edge_vc(road_class: str, road_name, scenario: Scenario, hour: int) -> float:
    """Full v/c for an edge that feeds the travel-time BPR term (tasks 6.2/6.3).

    Baseline v/c for the (road_class, hour) plus the E-suspension bump on
    Huntington Ave. ``road_name`` is the edge's OSM name (string or list); it
    only affects the result through the Huntington check.

    NOTE — monotonicity contract (Requirement 3.6, steering "Guarantees"):
    the demand drop (``demand_drop_factor`` / ``volume_vc``) is deliberately
    NOT applied here. The demand drop is a modeling convenience for "people
    stay home", but lowering v/c with snow lowers the BPR congestion term, and
    on a just-plowed edge (where the snow->capacity channel barely moves) that
    could make MORE snow produce a *faster* edge — breaking the invariant
    "more snow never makes any edge faster or any origin closer". The invariant
    is the contract, so the travel-time v/c uses the undropped baseline; the
    demand drop stays available via ``volume_vc`` for analytics that want it.
    """
    vc = base_vc(road_class, hour)
    vc += e_suspension_extra_vc(is_huntington_edge(road_name), scenario)
    return vc
