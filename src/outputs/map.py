"""City-view map rendering for the Storm Twin.

Owner: C (UI & map). This is the home for all Folium map construction and the
colour logic that goes with it, as assigned in design.md's file-ownership table
(`src/outputs/map.py`). ``app.py`` imports from here; later tasks (11.1
breaking-point map, 17 my-trip map) extend this module rather than ``app.py``.

Colour scheme (Requirement 11.4, task 7.1):
  Roads     coloured by capacity factor on a GREEN -> RED scale; a fully closed
            / impassable road (capacity factor 0) is drawn BLACK.
  Origins   coloured by minutes to the nearest hospital in four bands:
              <= 15 min        green
              15 - 30 min      orange
              > 30 min         red
              unreachable      grey  (minutes == inf)

The module only needs ``src.contract`` for the result shape and ``config`` for the
bounding box; it never reaches into the simulator internals.
"""

from __future__ import annotations

from typing import Any, Optional

import folium

from config.params import BBOX
from src.contract import SimResult

# Type alias: the scenario-independent geometry of the road network, mapping
# each ``(u, v, key)`` edge to the ``(lat, lon)`` polyline that draws it.
EdgeGeometry = dict[tuple[int, int, int], list[tuple[float, float]]]

# How many origin dots to draw by default before sampling kicks in. The study
# area has ~609 origins; drawing all of them keeps Folium responsive enough, but
# a cap keeps the map snappy when the origin set grows (e.g. a denser bbox) and
# during rapid slider drags. ``None`` (or a cap >= origin count) draws them all.
DEFAULT_MAX_ORIGINS = 300

# --------------------------------------------------------------------------- colours

# Road colours ----------------------------------------------------------------
# A fully closed road is pure black; everything open interpolates green -> red
# as the capacity factor falls from 1.0 toward 0.0.
ROAD_CLOSED_COLOR = "#000000"            # capacity factor == 0 (impassable)

# Anchors for the open-road gradient, from best to worst capacity.
#   1.0 -> green, 0.5 -> yellow/amber, ~0.0 -> red
_CAP_ANCHORS = [
    (1.0, (0x2E, 0xCC, 0x40)),   # green
    (0.5, (0xFF, 0xD7, 0x00)),   # amber (green->red midpoint)
    (0.0, (0xFF, 0x41, 0x36)),   # red
]

# Origin-dot bands ------------------------------------------------------------
ORIGIN_FAST_COLOR = "#2ecc40"        # <= 15 min   (green)
ORIGIN_MEDIUM_COLOR = "#ff8c00"      # 15 - 30 min (orange)
ORIGIN_SLOW_COLOR = "#ff4136"        # > 30 min    (red)
ORIGIN_UNREACHABLE_COLOR = "#808080"  # unreachable (grey)

ORIGIN_FAST_MAX_MIN = 15.0
ORIGIN_MEDIUM_MAX_MIN = 30.0

# Breaking-point origin dots (task 11.1, Requirements 15.4, 15.3, 11.4) --------
# ``sweep_snow`` reports, per origin, the first snowfall (in inches) at which it
# breaks, or ``None`` if it never breaks up to the sweep's ``max_inches``. We
# colour each origin on a RED -> GREEN gradient by that breaking point:
#   low inches  (fragile, breaks in a light storm)   -> red
#   high inches (robust, holds through a big storm)   -> green
#   never breaks                                       -> grey
# The gradient is anchored over 0..BREAKING_POINT_MAX_INCHES inches; anything at
# or above the top anchor is drawn at the "robust" green end.
BREAKING_POINT_NEVER_COLOR = "#808080"   # never breaks up to max_inches (grey)
BREAKING_POINT_MAX_INCHES = 30.0         # top of the gradient (matches sweep max)

# Anchors from fragile (low inches = red) to robust (high inches = green), with
# an amber midpoint so the scale reads red -> amber -> green as inches rise.
_BREAK_ANCHORS = [
    (0.0, (0xFF, 0x41, 0x36)),                        # breaks almost immediately -> red
    (BREAKING_POINT_MAX_INCHES / 2, (0xFF, 0xD7, 0x00)),  # mid -> amber
    (BREAKING_POINT_MAX_INCHES, (0x2E, 0xCC, 0x40)),  # holds to the top -> green
]


def capacity_color(cap: float) -> str:
    """Map a capacity factor (0..1) to a hex colour on a green -> red scale.

    A capacity factor of exactly 0 means the road is closed / impassable and is
    drawn black. Any positive capacity interpolates green (1.0) -> amber (0.5)
    -> red (approaching 0).
    """
    if cap <= 0.0:
        return ROAD_CLOSED_COLOR
    cap = min(1.0, cap)
    for i in range(len(_CAP_ANCHORS) - 1):
        hi, hc = _CAP_ANCHORS[i]
        lo, lc = _CAP_ANCHORS[i + 1]
        if lo <= cap <= hi:
            t = (cap - lo) / (hi - lo) if hi > lo else 0.0
            r = int(lc[0] + t * (hc[0] - lc[0]))
            g = int(lc[1] + t * (hc[1] - lc[1]))
            b = int(lc[2] + t * (hc[2] - lc[2]))
            return f"#{r:02x}{g:02x}{b:02x}"
    return ROAD_CLOSED_COLOR


def origin_color(minutes: float) -> str:
    """Origin-dot colour by minutes to the nearest hospital (four bands)."""
    if minutes == float("inf"):
        return ORIGIN_UNREACHABLE_COLOR
    if minutes <= ORIGIN_FAST_MAX_MIN:
        return ORIGIN_FAST_COLOR
    if minutes <= ORIGIN_MEDIUM_MAX_MIN:
        return ORIGIN_MEDIUM_COLOR
    return ORIGIN_SLOW_COLOR


def breaking_point_color(inches_to_break: Optional[float]) -> str:
    """Colour an origin by the snowfall (inches) at which it first breaks.

    This is the breaking-point counterpart to :func:`origin_color` (task 11.1,
    Requirement 15.4). Input is one value from a ``sweep_snow`` result:

      ``None``   the origin never breaks up to the sweep's ``max_inches`` ->
                 drawn grey (:data:`BREAKING_POINT_NEVER_COLOR`), the "robust,
                 off the scale" case.
      a float    the first snowfall at which the origin breaks. Low values are
                 fragile and drawn red; high values hold through a big storm and
                 are drawn green, interpolating red -> amber -> green over
                 0..:data:`BREAKING_POINT_MAX_INCHES` inches.

    A breaking point at or above the top anchor clamps to the robust green end;
    a negative value (shouldn't happen) clamps to the fragile red end.
    """
    if inches_to_break is None:
        return BREAKING_POINT_NEVER_COLOR
    x = max(0.0, min(float(inches_to_break), BREAKING_POINT_MAX_INCHES))
    for i in range(len(_BREAK_ANCHORS) - 1):
        lo, lc = _BREAK_ANCHORS[i]
        hi, hc = _BREAK_ANCHORS[i + 1]
        if lo <= x <= hi:
            t = (x - lo) / (hi - lo) if hi > lo else 0.0
            r = int(lc[0] + t * (hc[0] - lc[0]))
            g = int(lc[1] + t * (hc[1] - lc[1]))
            b = int(lc[2] + t * (hc[2] - lc[2]))
            return f"#{r:02x}{g:02x}{b:02x}"
    # x == top anchor exactly, or past the last segment -> robust green end.
    rr, gg, bb = _BREAK_ANCHORS[-1][1]
    return f"#{rr:02x}{gg:02x}{bb:02x}"


# --------------------------------------------------------------------------- geometry


def edge_coords(graph: Any, u: int, v: int, data: dict) -> list[tuple[float, float]]:
    """Extract ``(lat, lon)`` points along an edge, using its geometry if present."""
    if "geometry" in data:
        geom = data["geometry"]
        try:
            if hasattr(geom, "geoms"):          # MultiLineString
                return [(pt[1], pt[0]) for part in geom.geoms for pt in part.coords]
            if hasattr(geom, "coords"):          # LineString
                return [(pt[1], pt[0]) for pt in geom.coords]
        except Exception:
            pass
    # Fall back to the two endpoint nodes.
    nu, nv = graph.nodes[u], graph.nodes[v]
    return [(nu["y"], nu["x"]), (nv["y"], nv["x"])]


# Module-level geometry cache keyed on the graph's object identity. Building the
# per-edge polylines walks all ~1444 edges and is pure geometry — it does NOT
# depend on the scenario, so it should only happen once per loaded graph rather
# than on every slider move. ``app.py`` also wraps ``precompute_edge_geometry``
# in ``st.cache_resource`` for the Streamlit session; this dict makes direct
# callers (tests, scripts) equally cheap on the second build.
_GEOMETRY_CACHE: dict[int, EdgeGeometry] = {}


def precompute_edge_geometry(graph: Any) -> EdgeGeometry:
    """Build (once) and cache the per-edge ``(lat, lon)`` polylines for ``graph``.

    The geometry is scenario-independent: the shape of each road never changes
    when the snowfall slider moves, only its colour does. So we compute it once
    and reuse it on every subsequent render of the same graph.

    Keyed on ``id(graph)`` so repeated calls with the same loaded graph object
    (which is what ``st.cache_resource`` hands back each rerun) reuse the cached
    result. Returns an empty mapping when ``graph`` is ``None``.
    """
    if graph is None:
        return {}
    cached = _GEOMETRY_CACHE.get(id(graph))
    if cached is not None:
        return cached
    geometry: EdgeGeometry = {
        (u, v, key): edge_coords(graph, u, v, data)
        for u, v, key, data in graph.edges(keys=True, data=True)
    }
    _GEOMETRY_CACHE[id(graph)] = geometry
    return geometry


# --------------------------------------------------------------------------- legend


def add_legend(m: folium.Map) -> None:
    """Overlay an HTML legend explaining origin-dot and road colours."""
    legend = folium.Element(
        f"""
        <div style="position: fixed; bottom: 30px; left: 30px; z-index: 1000;
                    background: rgba(255,255,255,0.92); padding: 10px 14px;
                    border-radius: 6px; box-shadow: 0 2px 6px rgba(0,0,0,0.3);
                    font-size: 12px; font-family: Arial, sans-serif; line-height: 1.6;">
          <div style="font-weight: bold; margin-bottom: 4px;">Minutes to hospital</div>
          <div><span style="color:{ORIGIN_FAST_COLOR};">&#9679;</span> &le; 15 min</div>
          <div><span style="color:{ORIGIN_MEDIUM_COLOR};">&#9679;</span> 15&ndash;30 min</div>
          <div><span style="color:{ORIGIN_SLOW_COLOR};">&#9679;</span> &gt; 30 min</div>
          <div><span style="color:{ORIGIN_UNREACHABLE_COLOR};">&#9679;</span> Unreachable</div>
          <div style="margin-top: 8px; font-weight: bold; margin-bottom: 4px;">Road capacity</div>
          <div><span style="color:{capacity_color(1.0)};">&#9472;</span> Full (normal)</div>
          <div><span style="color:{capacity_color(0.5)};">&#9472;</span> Reduced</div>
          <div><span style="color:{capacity_color(0.15)};">&#9472;</span> Severely reduced</div>
          <div><span style="color:{ROAD_CLOSED_COLOR};">&#9472;</span> Closed</div>
        </div>
        """
    )
    m.get_root().html.add_child(legend)


# --------------------------------------------------------------------------- map builder


def _sample_origins(origins: list, max_origins: Optional[int]) -> list:
    """Return the origins to DRAW, capped at ``max_origins`` by even stepping.

    Sampling is for MAP DISPLAY only — the simulator still computes KPIs over the
    full origin set, so this never touches correctness, only how many dots the
    Folium map paints. When ``max_origins`` is ``None`` or at least the number of
    origins, every origin is drawn. Otherwise we draw every Nth origin so the kept
    set is spread evenly across the whole study area rather than clustered.
    """
    total = len(origins)
    if max_origins is None or max_origins <= 0 or total <= max_origins:
        return origins
    # Step chosen so ceil(total / step) <= max_origins; even spatial coverage.
    step = -(-total // max_origins)  # ceiling division
    return origins[::step]


def build_city_map(
    result: SimResult,
    graph: Any,
    edge_geometry: Optional[EdgeGeometry] = None,
    max_origins: Optional[int] = DEFAULT_MAX_ORIGINS,
) -> folium.Map:
    """Build a Folium map of the study area with roads and origin dots.

    Roads are drawn only when ``graph`` is not ``None`` (the GraphML cache from
    task 1.1 exists). Origin dots always render from the simulation results
    (Requirement 11.4).

    Performance (task 7.2):
      ``edge_geometry``  Precomputed ``(u, v, key) -> [(lat, lon), ...]`` polylines
                         (see :func:`precompute_edge_geometry`). The geometry is
                         scenario-independent, so passing it in — or letting this
                         function fetch it from the module cache — means the shapes
                         are built once and only the *colours* change when the
                         snowfall slider moves. ``app.py`` precomputes this under
                         ``st.cache_resource`` and hands it in on every rerun.
      ``max_origins``    Cap on how many origin DOTS are drawn (display only; KPIs
                         always use the full set). When the origin count exceeds the
                         cap, every Nth origin is drawn so the map stays responsive;
                         the full set is kept when under the cap. ``None`` draws all.
    """
    center_lat = (BBOX["north"] + BBOX["south"]) / 2
    center_lon = (BBOX["east"] + BBOX["west"]) / 2
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=14,
        tiles="OpenStreetMap",
    )

    # --- Roads (only if the cached graph is available) ---
    if graph is not None:
        # Geometry is built once and reused; only the colours below change per run.
        if edge_geometry is None:
            edge_geometry = precompute_edge_geometry(graph)
        cap_lookup: dict[tuple[int, int, int], float] = {
            (e["u"], e["v"], e["key"]): e["capacity_factor"]
            for e in result["edges"]
        }
        for edge_id, coords in edge_geometry.items():
            cap = cap_lookup.get(edge_id, 1.0)  # default: normal
            color = capacity_color(cap)         # <-- the only per-slider change
            if len(coords) >= 2:
                folium.PolyLine(
                    locations=coords,
                    color=color,
                    weight=3 if cap > 0 else 1,
                    opacity=0.7,
                    popup=f"Capacity: {cap:.0%}",
                ).add_to(m)

    # --- Origin dots (always rendered from simulation results; sampled for display) ---
    for origin in _sample_origins(result["origins"], max_origins):
        minutes = origin["minutes_to_hospital"]
        color = origin_color(minutes)
        hospital = origin.get("nearest_hospital") or "unknown"
        if minutes == float("inf"):
            tip = "Unreachable from any hospital"
        else:
            tip = f"{minutes:.0f} min to {hospital}"
        folium.CircleMarker(
            location=[origin["lat"], origin["lon"]],
            radius=5,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.8,
            tooltip=tip,
        ).add_to(m)

    add_legend(m)
    return m


# --------------------------------------------------------------------------- breaking-point map


def add_breaking_point_legend(m: folium.Map) -> None:
    """Overlay an HTML legend explaining the breaking-point origin colours.

    Mirrors :func:`add_legend` but for the inches-to-break scale drawn by
    :func:`build_breaking_point_map` (task 11.1, Requirement 15.4).
    """
    half = BREAKING_POINT_MAX_INCHES / 2
    legend = folium.Element(
        f"""
        <div style="position: fixed; bottom: 30px; left: 30px; z-index: 1000;
                    background: rgba(255,255,255,0.92); padding: 10px 14px;
                    border-radius: 6px; box-shadow: 0 2px 6px rgba(0,0,0,0.3);
                    font-size: 12px; font-family: Arial, sans-serif; line-height: 1.6;">
          <div style="font-weight: bold; margin-bottom: 4px;">Snow to cut off (inches)</div>
          <div><span style="color:{breaking_point_color(2.0)};">&#9679;</span> Breaks early (fragile)</div>
          <div><span style="color:{breaking_point_color(half)};">&#9679;</span> Breaks around {half:.0f} in</div>
          <div><span style="color:{breaking_point_color(BREAKING_POINT_MAX_INCHES)};">&#9679;</span> Holds to {BREAKING_POINT_MAX_INCHES:.0f} in (robust)</div>
          <div><span style="color:{BREAKING_POINT_NEVER_COLOR};">&#9679;</span> Never breaks</div>
          <div style="margin-top: 6px; font-style: italic; color: #555;">simulation estimate</div>
        </div>
        """
    )
    m.get_root().html.add_child(legend)


def join_sweep_with_origins(
    sweep_result: dict[int, Optional[float]],
    result: SimResult,
) -> list[dict]:
    """Join a ``sweep_snow`` result with origin coordinates from a ``SimResult``.

    ``sweep_snow`` returns only ``node -> inches-to-break`` (or ``None``); it
    carries no coordinates. ``run_simulation`` returns origins with ``lat``/
    ``lon``. This joins them on ``node`` so :func:`build_breaking_point_map` has
    everything it needs, and keeps that join logic in the C-owned map module
    rather than scattered in ``app.py``.

    Returns a list of ``{"node", "lat", "lon", "inches_to_break"}`` dicts, one
    per origin present in ``result`` that also appears in ``sweep_result``.
    Origins missing from the sweep are skipped (the two should cover the same
    node set, but we never invent data).
    """
    joined: list[dict] = []
    for origin in result["origins"]:
        node = origin["node"]
        if node not in sweep_result:
            continue
        joined.append(
            {
                "node": node,
                "lat": origin["lat"],
                "lon": origin["lon"],
                "inches_to_break": sweep_result[node],
            }
        )
    return joined


def build_breaking_point_map(
    origins_break: list[dict],
    graph: Any = None,
    edge_geometry: Optional[EdgeGeometry] = None,
    max_origins: Optional[int] = DEFAULT_MAX_ORIGINS,
) -> folium.Map:
    """Build a Folium map colouring each origin by its breaking-point snowfall.

    Task 11.1 / Requirements 15.4, 15.3, 11.4. This is the breaking-point
    counterpart to :func:`build_city_map`: instead of minutes-to-hospital for a
    single scenario hour, each origin is coloured by how much snow it takes to
    cut it off (from :func:`sweep_snow`), with "never breaks" origins in grey.

    ``origins_break`` is a list of ``{"node", "lat", "lon", "inches_to_break"}``
    dicts — build it with :func:`join_sweep_with_origins` from a ``sweep_snow``
    result and a ``run_simulation`` result (the sweep has no coordinates of its
    own).

    Roads are drawn in a neutral grey when ``graph`` is provided, so the origin
    colours carry the story; they are not recoloured per scenario here (the
    breaking-point view is a sweep across many snowfalls, not one hour). Geometry
    caching and origin sampling match :func:`build_city_map` for consistency and
    responsiveness (task 7.2).
    """
    center_lat = (BBOX["north"] + BBOX["south"]) / 2
    center_lon = (BBOX["east"] + BBOX["west"]) / 2
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=14,
        tiles="OpenStreetMap",
    )

    # --- Roads: neutral backdrop (the breaking-point story is in the dots) ---
    if graph is not None:
        if edge_geometry is None:
            edge_geometry = precompute_edge_geometry(graph)
        for coords in edge_geometry.values():
            if len(coords) >= 2:
                folium.PolyLine(
                    locations=coords,
                    color="#b0b0b0",
                    weight=2,
                    opacity=0.5,
                ).add_to(m)

    # --- Origin dots coloured by inches-to-break (sampled for display) ---
    for origin in _sample_origins(origins_break, max_origins):
        inches = origin.get("inches_to_break")
        color = breaking_point_color(inches)
        if inches is None:
            tip = "Never breaks (up to 30 in) · simulation estimate"
        else:
            tip = f"Breaks at {inches:.0f} in of snow · simulation estimate"
        folium.CircleMarker(
            location=[origin["lat"], origin["lon"]],
            radius=5,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.8,
            tooltip=tip,
        ).add_to(m)

    add_breaking_point_legend(m)
    return m


def count_broken_by(origins_break: list[dict], inches: float) -> int:
    """Count origins that break at or below ``inches`` of snowfall.

    Used by ``app.py`` for an honest one-line summary under the breaking-point
    map, e.g. "N origins break by 12 in". Origins that never break (``None``)
    are not counted.
    """
    n = 0
    for origin in origins_break:
        itb = origin.get("inches_to_break")
        if itb is not None and itb <= inches:
            n += 1
    return n
