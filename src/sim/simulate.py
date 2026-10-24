"""The real ``run_simulation`` core (task 6.3). Owner: B.

Pipeline for one ``run_simulation(scenario, hour)`` (design.md):

    cached drive graph (A)
      -> per edge: sim travel time from snow + capacity + v/c (travel.py)
      -> drop impassable edges (inf time) from the routing graph
      -> one multi-source Dijkstra from the 3 hospital nodes on the
         REVERSED graph -> minutes to nearest hospital for every origin
      -> OriginResults + KPIs

Everything heavy lives here so ``src/contract.py`` stays a thin shim. This
module only imports B-owned sim code plus A-owned read-only loaders
(network.py, hospitals.py); it never touches app.py or C/D files.

Requirements: 15.1 (minutes to nearest hospital, inf if unreachable),
15.2 (broken flag), 15.3 (KPIs), 16.1 (contract shapes), 7.4 (label).
"""
from __future__ import annotations

import math

import networkx as nx

from config.params import BROKEN_MINUTES, SWEEP_MAX_IN, SWEEP_STEP_IN
from src.contract import (
    EdgeResult,
    KPIs,
    OriginResult,
    Scenario,
    SimResult,
    TripResult,
)
from src.sim.snow import snow_on_road
from src.sim.travel import edge_sim_time, effective_capacity_factor
from src.twin.hospitals import load_hospitals
from src.twin.network import load_drive_graph
from src.twin.transit import load_transit_stops

# The attribute name we write the congested travel time to on each edge.
SIM_TIME_ATTR = "sim_time"


# ---------------------------------------------------------------- graph cache

_GRAPH_CACHE: nx.MultiDiGraph | None = None


def _get_graph() -> nx.MultiDiGraph:
    """Return the cached drive graph, loading it once per process.

    C wires Streamlit's ``st.cache_resource`` around its own loader in app.py;
    here we just memoize so repeated ``run_simulation`` calls in one process
    (the sweep, tests) don't reload the GraphML every time.
    """
    global _GRAPH_CACHE
    if _GRAPH_CACHE is None:
        _GRAPH_CACHE = load_drive_graph()
    return _GRAPH_CACHE


# ---------------------------------------------------------------- edges (step 1-2)

def _edge_results_and_sim_times(
    G: nx.MultiDiGraph, scenario: Scenario, hour: int
) -> tuple[list[EdgeResult], dict[tuple[int, int, int], float]]:
    """Compute the congested sim time for every edge.

    Returns the EdgeResult list (contract shape) and a ``{(u, v, key): sim_time}``
    map used to weight the search graph. Impassable edges keep ``inf`` here;
    they are skipped when the routing graph is built (step 2).
    """
    edges: list[EdgeResult] = []
    sim_times: dict[tuple[int, int, int], float] = {}

    for u, v, key, data in G.edges(keys=True, data=True):
        free_flow_s = float(data.get("travel_time", 0.0) or 0.0)
        road_class = data.get("road_class", "side")
        road_name = data.get("name")

        t = edge_sim_time(free_flow_s, road_class, road_name, scenario, hour)
        snow_in = snow_on_road(road_class, scenario, hour)

        # effective_capacity_factor already folds snow + parked-car losses; it
        # is the exact factor behind this edge's sim time (0.0 = impassable).
        cap = effective_capacity_factor(road_class, road_name, scenario, hour)

        edges.append({
            "u": int(u),
            "v": int(v),
            "key": int(key),
            "capacity_factor": float(cap),
            "travel_time_s": float(t),
            "snow_on_road_in": float(snow_in),
        })
        sim_times[(int(u), int(v), int(key))] = float(t)

    return edges, sim_times


def _build_routing_graph(
    G: nx.MultiDiGraph, sim_times: dict[tuple[int, int, int], float]
) -> nx.DiGraph:
    """Build a lightweight directed graph with only passable edges (step 2).

    Impassable edges (``inf`` sim time) are skipped so Dijkstra never traverses
    them (Requirement 3.4 / 15.1). Parallel edges collapse to the fastest one,
    which is all shortest-path routing needs.
    """
    R = nx.DiGraph()
    R.add_nodes_from(G.nodes())
    for (u, v, _key), t in sim_times.items():
        if not math.isfinite(t):
            continue
        existing = R.get_edge_data(u, v)
        if existing is None or t < existing[SIM_TIME_ATTR]:
            R.add_edge(u, v, **{SIM_TIME_ATTR: t})
    return R


# ---------------------------------------------------------------- origins (step 3)

def _origin_nodes(G: nx.MultiDiGraph) -> list[int]:
    """Origins are intersections: nodes with street_count >= 3 (design.md)."""
    origins: list[int] = []
    for n, data in G.nodes(data=True):
        try:
            sc = int(data.get("street_count") or 0)
        except (TypeError, ValueError):
            sc = 0
        if sc >= 3:
            origins.append(int(n))
    return origins


# ---------------------------------------------------------------- Dijkstra (step 4)

def _minutes_and_nearest(
    R: nx.DiGraph, hospitals: list[dict]
) -> tuple[dict[int, float], dict[int, str]]:
    """One multi-source Dijkstra on the REVERSED graph (design.md speed tip).

    Routing on ``R.reverse`` from the hospital nodes gives, for every origin,
    the cost of the shortest *origin -> hospital* path (the reverse of a
    *hospital -> origin* path), i.e. minutes to the nearest hospital, in a
    single call (Requirement 15.1).

    We use ``multi_source_dijkstra`` (lengths + paths) so the hospital that
    actually serves each origin is the source end of its path; that lets us
    label ``nearest_hospital`` exactly without a second search.
    """
    node_to_name: dict[int, str] = {}
    sources: set[int] = set()
    for h in hospitals:
        node = int(h["node"])
        sources.add(node)
        # If two hospitals snap to the same node, first one wins the label.
        node_to_name.setdefault(node, str(h.get("name") or ""))

    reversed_graph = R.reverse(copy=False)

    # Only keep sources that exist in the graph (defensive: a hospital could
    # snap to a node that was truncated out of the cached graph).
    present_sources = [s for s in sources if reversed_graph.has_node(s)]
    if not present_sources:
        return {}, {}

    lengths, paths = nx.multi_source_dijkstra(
        reversed_graph, present_sources, weight=SIM_TIME_ATTR
    )

    nearest: dict[int, str] = {}
    for node, path in paths.items():
        # path[0] is the source (a hospital node) in the reversed graph.
        src = path[0]
        nearest[node] = node_to_name.get(src, "")

    return lengths, nearest


# ---------------------------------------------------------------- assemble

def _origin_results(
    G: nx.MultiDiGraph,
    origins: list[int],
    seconds: dict[int, float],
    nearest: dict[int, str],
) -> list[OriginResult]:
    """Turn Dijkstra output into OriginResults (step 5, Requirements 15.1-15.2)."""
    results: list[OriginResult] = []
    for node in origins:
        nd = G.nodes[node]
        lat = float(nd.get("y"))
        lon = float(nd.get("x"))

        sec = seconds.get(node)
        if sec is None or not math.isfinite(sec):
            minutes = math.inf
            name: str | None = None
            broken = True
        else:
            minutes = sec / 60.0
            name = nearest.get(node) or None
            broken = minutes > BROKEN_MINUTES

        results.append({
            "node": int(node),
            "lat": lat,
            "lon": lon,
            "minutes_to_hospital": float(minutes),
            "nearest_hospital": name,
            "broken": bool(broken),
        })
    return results


def _kpis(origins: list[OriginResult]) -> KPIs:
    """KPIs over the origins (step 6, Requirement 15.3).

    ``avg_minutes_to_hospital`` averages reachable origins only; unreachable
    origins (inf minutes) are counted in ``n_unreachable`` and excluded from the
    average so one unreachable point can't blow the mean up to infinity.
    """
    total = len(origins)
    reachable = [o["minutes_to_hospital"] for o in origins
                 if math.isfinite(o["minutes_to_hospital"])]
    n_unreachable = total - len(reachable)
    n_broken = sum(1 for o in origins if o["broken"])

    pct_broken = (100.0 * n_broken / total) if total else 0.0
    avg_minutes = (sum(reachable) / len(reachable)) if reachable else math.inf

    return {
        "pct_broken": float(pct_broken),
        "avg_minutes_to_hospital": float(avg_minutes),
        "n_unreachable": int(n_unreachable),
    }


# ---------------------------------------------------------------- entry point

def run_simulation(scenario: Scenario, hour: int) -> SimResult:
    """Run one storm scenario at a clock ``hour`` and return a SimResult.

    This is the real body behind ``src.contract.run_simulation``; the contract
    function is a one-line shim so its TypedDict shapes stay the single source
    of truth (Requirement 16.1).
    """
    G = _get_graph()

    edges, sim_times = _edge_results_and_sim_times(G, scenario, hour)
    R = _build_routing_graph(G, sim_times)
    origins = _origin_nodes(G)

    hospitals = load_hospitals()
    seconds, nearest = _minutes_and_nearest(R, hospitals)

    origin_results = _origin_results(G, origins, seconds, nearest)
    kpis = _kpis(origin_results)

    return {
        "hour": int(hour),
        "edges": edges,
        "origins": origin_results,
        "kpis": kpis,
        "label": "simulation estimate",  # Requirement 7.4
    }


# ---------------------------------------------------------------- sweep (task 10.1)

def sweep_levels(max_inches: int = SWEEP_MAX_IN,
                 step: int = SWEEP_STEP_IN) -> list[int]:
    """The snowfall levels of the breaking-point sweep (Requirement 15.4).

    0, step, 2*step, ... up to and including ``max_inches``. With the defaults
    (max 30, step 2) that is 16 levels: 0, 2, 4, ..., 30.
    """
    levels = list(range(0, int(max_inches) + 1, int(step)))
    # Make sure the top of the range is covered even if step doesn't divide it.
    if levels and levels[-1] != int(max_inches):
        levels.append(int(max_inches))
    return levels


def _scenario_at_snow(scenario: Scenario, snow_inches: float) -> Scenario:
    """A shallow copy of ``scenario`` with ``snow_inches`` overridden.

    Everything else (start hour, duration, parking, E suspension, elevators)
    is held fixed so the sweep isolates the effect of total snowfall.
    """
    sc: Scenario = dict(scenario)  # type: ignore[assignment]
    sc["snow_inches"] = float(snow_inches)
    return sc


def _sweep_hour(scenario: Scenario, hour: int | None) -> int:
    """Default the sweep's evaluation hour to the end of the storm.

    ``start_hour + duration_hours`` (per the contract stub docstring) is when
    side-street snow peaks, i.e. the worst moment for hospital access. A caller
    may pass an explicit ``hour`` to override it.
    """
    if hour is not None:
        return int(hour)
    start = int(scenario.get("start_hour", 0) or 0)
    duration = int(scenario.get("duration_hours", 0) or 0)
    return start + duration


def _broken_nodes_at(
    G: nx.MultiDiGraph,
    origins: list[int],
    sources: list[int],
    scenario: Scenario,
    hour: int,
) -> set[int]:
    """Origins that are broken for ``scenario`` at ``hour`` (Requirement 15.2).

    A lighter core than ``run_simulation``: it only needs the broken/not-broken
    decision per origin, so it skips building EdgeResults and KPIs. It reuses
    the same edge-weight model (``edge_sim_time``), routing-graph construction
    and single reversed multi-source Dijkstra, so a sweep level matches what
    ``run_simulation`` would report as ``broken`` at the same snow/hour.

    An origin is broken when its minutes to the nearest hospital exceed
    BROKEN_MINUTES or no route exists (it is absent from the Dijkstra lengths).
    """
    # Only edge weights change per level; recompute them and nothing else.
    sim_times: dict[tuple[int, int, int], float] = {}
    for u, v, key, data in G.edges(keys=True, data=True):
        free_flow_s = float(data.get("travel_time", 0.0) or 0.0)
        road_class = data.get("road_class", "side")
        road_name = data.get("name")
        sim_times[(int(u), int(v), int(key))] = edge_sim_time(
            free_flow_s, road_class, road_name, scenario, hour
        )

    R = _build_routing_graph(G, sim_times)

    present_sources = [s for s in sources if R.has_node(s)]
    broken: set[int] = set()
    if not present_sources:
        # No hospital reachable in the graph at all: every origin is broken.
        return set(origins)

    seconds = nx.multi_source_dijkstra_path_length(
        R.reverse(copy=False), present_sources, weight=SIM_TIME_ATTR
    )

    threshold_s = BROKEN_MINUTES * 60.0
    for node in origins:
        sec = seconds.get(node)
        if sec is None or not math.isfinite(sec) or sec > threshold_s:
            broken.add(node)
    return broken


def sweep_snow(scenario: Scenario, hour: int | None = None,
               max_inches: int = SWEEP_MAX_IN,
               step: int = SWEEP_STEP_IN) -> dict[int, float | None]:
    """Breaking-point sweep (task 10.1, Requirement 15.4).

    For snowfall levels 0, step, ..., ``max_inches`` (16 levels at the defaults),
    rebuild the scenario at that snowfall and record, for every origin, the
    FIRST (lowest) level at which it breaks. Origins that never break up to
    ``max_inches`` map to ``None``.

    Speed (design.md): the drive graph, origin set and hospital sources are
    loaded/computed once; only the per-edge weights are recomputed per level,
    and each level is a single reversed multi-source Dijkstra. That makes the
    whole sweep ~16 shortest-path calls -- seconds, not minutes.

    Returns ``{origin_node: first_break_inches | None}`` over the same origin
    set ``run_simulation`` uses (intersections, street_count >= 3).
    """
    G = _get_graph()
    origins = _origin_nodes(G)
    sources = [int(h["node"]) for h in load_hospitals()]

    eval_hour = _sweep_hour(scenario, hour)
    levels = sweep_levels(max_inches, step)

    # None until an origin first breaks; then the lowest level that broke it.
    first_break: dict[int, float | None] = {node: None for node in origins}
    remaining = set(origins)

    for level in levels:
        if not remaining:
            break  # every origin has already broken at a lower level
        sc = _scenario_at_snow(scenario, level)
        broken = _broken_nodes_at(G, origins, sources, sc, eval_hour)
        newly_broken = remaining & broken
        for node in newly_broken:
            first_break[node] = float(level)
        remaining -= newly_broken

    return first_break


# ---------------------------------------------------------------- trip time (task 10.2)

def _nearest_node(G: nx.MultiDiGraph, lat: float, lon: float) -> int:
    """Snap a (lat, lon) to the nearest drive-graph node (OSMnx nearest_nodes).

    OSMnx's ``nearest_nodes`` takes (G, X=lon, Y=lat). Mirrors the snapping A
    does in hospitals.py so a trip's endpoints land on the same node ids the
    rest of the twin uses. Tolerant of OSMnx v1/v2 import layout.
    """
    import osmnx as ox
    try:
        return int(ox.nearest_nodes(G, lon, lat))
    except AttributeError:  # pragma: no cover - very old OSMnx
        return int(ox.distance.nearest_nodes(G, lon, lat))


def _clear_day_scenario(scenario: Scenario) -> Scenario:
    """A baseline, clear-day twin of ``scenario`` (task 10.2, Requirement 16.3).

    Zero snowfall, full parking compliance and the E branch running, holding the
    storm's timing fixed (same start/duration, evaluated at the same hour). This
    is the free-flow reference the storm trip is compared against to work out how
    much earlier a traveller must leave.
    """
    sc: Scenario = dict(scenario)  # type: ignore[assignment]
    sc["snow_inches"] = 0.0
    sc["parking_compliance"] = 1.0
    sc["green_e_suspended"] = False
    return sc


def _routing_graph_for(G: nx.MultiDiGraph, scenario: Scenario,
                       hour: int) -> nx.DiGraph:
    """Build the passable-edge routing graph for one scenario+hour.

    A lighter path than full ``run_simulation``: it only needs per-edge sim
    times (same ``edge_sim_time`` model) to weight the graph, so it skips
    EdgeResults, origins and KPIs. Reuses ``_build_routing_graph`` so trip
    routing matches hospital-access routing edge for edge.
    """
    sim_times: dict[tuple[int, int, int], float] = {}
    for u, v, key, data in G.edges(keys=True, data=True):
        free_flow_s = float(data.get("travel_time", 0.0) or 0.0)
        road_class = data.get("road_class", "side")
        road_name = data.get("name")
        sim_times[(int(u), int(v), int(key))] = edge_sim_time(
            free_flow_s, road_class, road_name, scenario, hour
        )
    return _build_routing_graph(G, sim_times)


def _shortest_minutes(R: nx.DiGraph, src: int, dst: int) -> tuple[float, list[int]]:
    """Shortest ``src -> dst`` travel time in minutes and the node path.

    Returns ``(inf, [])`` when no route exists (or either endpoint is missing
    from the routing graph). A zero-length trip (src == dst) is 0 minutes with a
    single-node path.
    """
    if src == dst:
        return 0.0, [src]
    if not (R.has_node(src) and R.has_node(dst)):
        return math.inf, []
    try:
        seconds, path = nx.single_source_dijkstra(
            R, src, target=dst, weight=SIM_TIME_ATTR
        )
    except nx.NetworkXNoPath:
        return math.inf, []
    return float(seconds) / 60.0, [int(n) for n in path]


def _elevator_warnings(scenario: Scenario) -> list[str]:
    """Human-readable elevator warnings for stops in ``elevators_out``.

    For each MBTA stop id in ``scenario["elevators_out"]`` we look the stop up in
    the cached transit stops and surface ``"Elevator out at <stop name>"``
    (Requirement 16.3). Unknown ids fall back to the raw id so nothing is lost.
    An empty ``elevators_out`` yields no warnings.
    """
    out_ids = scenario.get("elevators_out") or []
    if not out_ids:
        return []

    name_by_id: dict[str, str] = {}
    try:
        data = load_transit_stops()
        for stop in data.get("stops", []):
            sid = stop.get("id")
            if sid is not None:
                name_by_id[str(sid)] = str(stop.get("name") or sid)
    except Exception:  # pragma: no cover - cache missing/offline; still warn by id
        name_by_id = {}

    warnings: list[str] = []
    for sid in out_ids:
        name = name_by_id.get(str(sid), str(sid))
        warnings.append(f"Elevator out at {name}")
    return warnings


def trip_time(origin: tuple[float, float], dest: tuple[float, float],
              scenario: Scenario, hour: int) -> TripResult:
    """Storm vs clear-day drive from ``origin`` to ``dest`` (task 10.2, Req 16.3).

    ``origin`` and ``dest`` are ``(lat, lon)`` tuples. Both are snapped to the
    nearest drive-graph node, then routed twice: once under the storm
    ``scenario`` at ``hour`` and once under a clear-day baseline (zero snow, full
    parking compliance, E branch running) at the same hour.

    Returns a TripResult (contract shape, unchanged):
      * ``minutes`` -- storm travel time; ``inf`` if no route exists.
      * ``clear_day_minutes`` -- the same trip on a clear day (free-flow ref).
      * ``broken`` -- storm minutes exceed BROKEN_MINUTES, or no route
        (Requirement 15.2's threshold applied to a single trip).
      * ``leave_earlier_by_min`` -- ``max(0, storm - clear_day)``; how much
        earlier to leave than on a clear day, never negative (Requirement 16.3).
      * ``route_nodes`` -- the storm node path (origin-snap -> dest-snap).
      * ``warnings`` -- e.g. an elevator-outage note per stop in
        ``elevators_out`` (Requirement 16.3).
    """
    G = _get_graph()

    o_node = _nearest_node(G, float(origin[0]), float(origin[1]))
    d_node = _nearest_node(G, float(dest[0]), float(dest[1]))

    storm_R = _routing_graph_for(G, scenario, hour)
    storm_minutes, route_nodes = _shortest_minutes(storm_R, o_node, d_node)

    clear_R = _routing_graph_for(G, _clear_day_scenario(scenario), hour)
    clear_minutes, _clear_route = _shortest_minutes(clear_R, o_node, d_node)

    broken = (not math.isfinite(storm_minutes)) or storm_minutes > BROKEN_MINUTES

    if math.isfinite(storm_minutes) and math.isfinite(clear_minutes):
        leave_earlier = max(0.0, storm_minutes - clear_minutes)
    else:
        # No storm route (or no clear-day route to compare against): there is no
        # meaningful "leave earlier" amount, so report 0.
        leave_earlier = 0.0

    return {
        "minutes": float(storm_minutes),
        "clear_day_minutes": float(clear_minutes),
        "broken": bool(broken),
        "leave_earlier_by_min": float(leave_earlier),
        "route_nodes": route_nodes,
        "warnings": _elevator_warnings(scenario),
    }
