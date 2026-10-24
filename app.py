"""Storm Twin — Streamlit entry point.

Owner: C (UI & map).

This app is the public face of the Storm Twin simulator. It lets a user dial up a
storm scenario with a few sliders, runs the simulator through the fixed contract in
``src/contract.py``, and shows what happens to hospital access across Longwood and
Fenway.

Imports are restricted to ``src.contract`` and ``config`` (see the project rules):
the UI never reaches into the simulator internals.

Tabs:
  - City view  — KPI cards + a Folium map of road/origin status.
  - My trips   — one persona's trip check (placeholder for now).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import folium
import streamlit as st
from streamlit_folium import st_folium

from config.params import BBOX
from src.contract import Scenario, SimResult, run_simulation

if TYPE_CHECKING:
    import networkx as nx

# Cached OSMnx drive graph (created by task 1.1; may not exist yet).
GRAPH_CACHE = Path(__file__).resolve().parent / "data" / "cache" / "drive_graph.graphml"


# --------------------------------------------------------------------------- color helpers

# Anchor colors for capacity interpolation: 1.0 = green, 0.5 = yellow, 0.0 = black
_CAP_ANCHORS = [
    (1.0, (0x2E, 0xCC, 0x40)),   # green
    (0.5, (0xFF, 0xD7, 0x00)),   # gold / yellow
    (0.0, (0x1A, 0x1A, 0x1A)),   # near-black
]


def _capacity_color(cap: float) -> str:
    """Map a capacity factor (0..1) to a hex color.

    1.0 -> green, 0.5 -> yellow, 0.0 -> near-black (closed).
    """
    cap = max(0.0, min(1.0, cap))
    for i in range(len(_CAP_ANCHORS) - 1):
        hi, hc = _CAP_ANCHORS[i]
        lo, lc = _CAP_ANCHORS[i + 1]
        if lo <= cap <= hi:
            t = (cap - lo) / (hi - lo) if hi > lo else 0.0
            r = int(lc[0] + t * (hc[0] - lc[0]))
            g = int(lc[1] + t * (hc[1] - lc[1]))
            b = int(lc[2] + t * (hc[2] - lc[2]))
            return f"#{r:02x}{g:02x}{b:02x}"
    return "#1a1a1a"


def _origin_color(minutes: float) -> str:
    """Origin-dot color by minutes to the nearest hospital."""
    if minutes == float("inf"):
        return "#1a1a1a"   # dark — unreachable
    if minutes <= 15:
        return "#2ecc40"   # green
    if minutes <= 30:
        return "#ff8c00"   # orange
    return "#ff4136"       # red


# --------------------------------------------------------------------------- graph + map


@st.cache_resource
def load_drive_graph() -> Any:
    """Load the cached OSMnx drive graph from GraphML if it exists.

    Returns the graph when the cache file is present, or ``None`` when it is
    not (task 1.1 creates the file). Until then the map renders without road
    edges — graceful degradation.
    """
    if not GRAPH_CACHE.exists():
        return None
    try:
        import osmnx as ox
        return ox.load_graphml(filepath=str(GRAPH_CACHE))
    except Exception:
        return None


def _edge_coords(graph: Any, u: int, v: int, data: dict) -> list[tuple[float, float]]:
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


def _add_legend(m: folium.Map) -> None:
    """Overlay an HTML legend explaining origin-dot and road colors."""
    legend = folium.Element(
        """
        <div style="position: fixed; bottom: 30px; left: 30px; z-index: 1000;
                    background: rgba(255,255,255,0.92); padding: 10px 14px;
                    border-radius: 6px; box-shadow: 0 2px 6px rgba(0,0,0,0.3);
                    font-size: 12px; font-family: Arial, sans-serif; line-height: 1.6;">
          <div style="font-weight: bold; margin-bottom: 4px;">Minutes to hospital</div>
          <div><span style="color:#2ecc40;">&#9679;</span> &le; 15 min</div>
          <div><span style="color:#ff8c00;">&#9679;</span> 15&ndash;30 min</div>
          <div><span style="color:#ff4136;">&#9679;</span> &gt; 30 min</div>
          <div><span style="color:#1a1a1a;">&#9679;</span> Unreachable</div>
          <div style="margin-top: 8px; font-weight: bold; margin-bottom: 4px;">Roads</div>
          <div><span style="color:#2ecc40;">&#9472;</span> Normal</div>
          <div><span style="color:#ffd700;">&#9472;</span> Reduced</div>
          <div><span style="color:#1a1a1a;">&#9472;</span> Closed</div>
        </div>
        """
    )
    m.get_root().html.add_child(legend)


def build_city_map(result: SimResult, graph: Any) -> folium.Map:
    """Build a Folium map of the study area with roads and origin dots.

    Roads are drawn only when ``graph`` is not ``None`` (GraphML cache exists).
    Origin dots always render from the simulation results (Requirement 11.4).
    """
    center_lat = (BBOX["north"] + BBOX["south"]) / 2
    center_lon = (BBOX["east"] + BBOX["west"]) / 2
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=14,
        tiles="cartodbpositron",
    )

    # --- Roads (only if the cached graph is available) ---
    if graph is not None:
        cap_lookup: dict[tuple[int, int, int], float] = {
            (e["u"], e["v"], e["key"]): e["capacity_factor"]
            for e in result["edges"]
        }
        for u, v, key, data in graph.edges(keys=True, data=True):
            cap = cap_lookup.get((u, v, key), 1.0)  # default: normal
            color = _capacity_color(cap)
            coords = _edge_coords(graph, u, v, data)
            if len(coords) >= 2:
                folium.PolyLine(
                    locations=coords,
                    color=color,
                    weight=3 if cap > 0 else 1,
                    opacity=0.7,
                    popup=f"Capacity: {cap:.0%}",
                ).add_to(m)

    # --- Origin dots (always rendered from simulation results) ---
    for origin in result["origins"]:
        minutes = origin["minutes_to_hospital"]
        color = _origin_color(minutes)
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

    _add_legend(m)
    return m


# --------------------------------------------------------------------------- scenario helpers


def build_scenario(
    snow_inches: float,
    start_hour: int,
    duration_hours: int,
    parking_compliance: float,
    green_e_suspended: bool,
) -> Scenario:
    """Assemble the scenario dict from sidebar inputs.

    Matches the ``Scenario`` TypedDict in ``src/contract.py``. ``elevators_out``
    defaults to an empty list; a live-data integration (later) will fill it from
    MBTA elevator alerts.
    """
    scenario: Scenario = {
        "snow_inches": snow_inches,
        "start_hour": start_hour,
        "duration_hours": duration_hours,
        "parking_compliance": parking_compliance,
        "green_e_suspended": green_e_suspended,
        "elevators_out": [],
    }
    return scenario


def render_kpi_cards(result: SimResult) -> None:
    """Show the three headline KPIs as metric cards.

    Every number is labelled a "simulation estimate" (Requirement 7.4): these are
    rule-based model outputs, not measurements.
    """
    kpis = result["kpis"]
    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Origins broken",
        f"{kpis['pct_broken']:.0f}%",
        help="Share of origins that need more than 30 min to reach a hospital, "
        "or cannot reach one at all.",
    )
    col2.metric(
        "Avg minutes to hospital",
        f"{kpis['avg_minutes_to_hospital']:.1f} min",
        help="Average over origins that can still reach a hospital.",
    )
    col3.metric(
        "Unreachable origins",
        f"{kpis['n_unreachable']}",
        help="Origins with no route to any hospital under this scenario.",
    )


# --------------------------------------------------------------------------- page


def main() -> None:
    st.set_page_config(
        page_title="Storm Twin — Longwood & Fenway",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("Storm Twin")
    st.caption("Can the people with the least slack still reach Longwood's hospitals in a storm?")

    # --- Sidebar: scenario controls ------------------------------------------
    st.sidebar.header("Storm scenario")

    snow_inches = st.sidebar.slider(
        "Snowfall (inches)",
        min_value=0.0,
        max_value=30.0,
        value=14.0,
        step=0.5,
        help="Total storm snowfall, spread evenly over the duration.",
    )
    start_hour = st.sidebar.slider(
        "Start hour",
        min_value=0,
        max_value=23,
        value=7,
        step=1,
        help="Hour of day the snow begins (0-23).",
    )
    duration_hours = st.sidebar.slider(
        "Duration (hours)",
        min_value=1,
        max_value=24,
        value=10,
        step=1,
        help="Length of the storm; snow is spread evenly over this window.",
    )
    hour_to_view = st.sidebar.slider(
        "Hour to view",
        min_value=0,
        max_value=23,
        value=8,
        step=1,
        help="Hour of day at which to evaluate conditions on the map.",
    )
    parking_compliance = st.sidebar.slider(
        "Cars moved off priority routes",
        min_value=0.0,
        max_value=1.0,
        value=0.6,
        step=0.05,
        format="%.0f%%",
        help="Share of cars moved off snow-emergency routes. Lower compliance "
        "cuts priority-route capacity and plowing effectiveness.",
    )
    green_e_suspended = st.sidebar.checkbox(
        "Green Line E suspended",
        value=False,
        help="E branch down pushes more cars onto Huntington Avenue.",
    )

    # --- Build the scenario and run the simulator ----------------------------
    scenario = build_scenario(
        snow_inches=snow_inches,
        start_hour=start_hour,
        duration_hours=duration_hours,
        parking_compliance=parking_compliance,
        green_e_suspended=green_e_suspended,
    )

    # The contract is the only API the UI is allowed to call (Requirement 16.1).
    result: SimResult = run_simulation(scenario, hour_to_view)

    # --- Two tabs (per design.md) --------------------------------------------
    tab_city, tab_trips = st.tabs(["City view", "My trips"])

    with tab_city:
        render_kpi_cards(result)

        # Small scenario recap so the numbers always have context.
        recap = (
            f"{snow_inches:.1f} in of snow starting at {start_hour:02d}:00 over "
            f"{duration_hours} h - viewing {hour_to_view:02d}:00"
        )
        if green_e_suspended:
            recap += " - Green Line E suspended"
        st.caption(recap)

        # --- Folium map (Requirement 11.4) -----------------------------------
        st.subheader("Hospital access map")

        # The road graph is loaded once and cached (task 1.1 creates the
        # GraphML; until then the map renders origins only).
        graph = load_drive_graph()
        city_map = build_city_map(result, graph)
        st_folium(city_map, width=800, height=500, returned_objects=[])

        if graph is None:
            st.caption(
                "Road network not loaded yet — the GraphML cache is created "
                "in task 1.1. Origin dots are shown from the simulation results."
            )
        st.caption(f"{len(result['origins'])} origins simulated · simulation estimate")

    with tab_trips:
        st.subheader("My trips")
        st.info(
            "Coming soon. This tab will run one persona's trip through the twin "
            "under live conditions and recommend when to leave and how to get there."
        )


if __name__ == "__main__":
    main()
