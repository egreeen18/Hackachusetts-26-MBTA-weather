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

import streamlit as st
from streamlit_folium import st_folium

from config.scenarios import SCENARIOS
from src.contract import Scenario, SimResult, run_simulation, sweep_snow
from src.outputs.map import (
    build_breaking_point_map,
    build_city_map,
    count_broken_by,
    join_sweep_with_origins,
    precompute_edge_geometry,
)

# Dropdown sentinel for the hand-tuned sliders path (no preset selected).
CUSTOM_PRESET_LABEL = "Custom (use sliders)"

# Cap on how many origin dots the city map draws (display only; the simulator
# still computes KPIs over every origin). Keeps the Folium map responsive while
# the user drags the snowfall slider. See src/outputs/map.py.
MAP_MAX_ORIGINS = 300

if TYPE_CHECKING:
    import networkx as nx

# Cached OSMnx drive graph (created by task 1.1 in src/twin/network.py, which
# saves it as drive.graphml; may not exist yet on a fresh checkout).
GRAPH_CACHE = Path(__file__).resolve().parent / "data" / "cache" / "drive.graphml"


# --------------------------------------------------------------------------- graph + map
#
# The map-building and colour logic lives in ``src/outputs/map.py`` (the C-owned
# module named in design.md's file-ownership table). ``build_city_map`` is
# imported above; later tasks (11.1 breaking-point map, 17 my-trip map) extend
# that module rather than this file.


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


@st.cache_resource
def load_edge_geometry(_graph: Any) -> Any:
    """Precompute the per-edge map polylines once and cache them for the session.

    The geometry (each road's ``(lat, lon)`` shape) never changes with the
    scenario — only the colour does — so building it on every slider move is pure
    waste. Caching it with ``st.cache_resource`` means it is computed once per
    loaded graph; ``build_city_map`` then just recolours those shapes per run.

    The parameter is named ``_graph`` so Streamlit skips trying to hash the graph
    (it is already a cached resource); identity is what matters.
    """
    return precompute_edge_geometry(_graph)


@st.cache_data(show_spinner="Running the breaking-point sweep (0-30 in)...")
def run_sweep(scenario_items: tuple) -> dict:
    """Cached ``sweep_snow`` keyed on the scenario contents.

    The sweep runs the simulator 16 times (0-30 in in 2-in steps), so it is far
    too slow to redo on every rerun. Streamlit's ``cache_data`` memoises it on
    the scenario, so it only recomputes when the user changes the scenario
    (via sliders or a preset). The scenario is passed as a sorted tuple of
    ``(key, value)`` pairs because a dict isn't hashable (and ``elevators_out``
    is turned into a tuple inside).
    """
    scenario: Scenario = dict(scenario_items)  # type: ignore[assignment]
    return sweep_snow(scenario)


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

    # Preset dropdown (task 11.1): one of D's demo scenarios, or "Custom" to drive
    # the sliders by hand. When a preset is picked, its contract-shaped scenario
    # and default view-hour override the sliders below (the sliders still show,
    # pre-filled, so the user can see what the preset chose and then switch to
    # Custom to tweak).
    preset_labels = [CUSTOM_PRESET_LABEL] + [p["label"] for p in SCENARIOS.values()]
    # Map label -> preset key for lookup after selection.
    label_to_key = {p["label"]: key for key, p in SCENARIOS.items()}
    chosen_label = st.sidebar.selectbox(
        "Preset scenario",
        options=preset_labels,
        index=0,
        help="Pick one of the demo scenarios, or keep Custom to set the sliders "
        "yourself. A preset fills in the sliders and the view hour for you.",
    )
    active_preset = (
        SCENARIOS[label_to_key[chosen_label]]
        if chosen_label != CUSTOM_PRESET_LABEL
        else None
    )
    if active_preset is not None:
        st.sidebar.caption(active_preset["blurb"])

    # Preset values seed the slider defaults; Custom falls back to the originals.
    if active_preset is not None:
        ps = active_preset["scenario"]
        default_snow = float(ps["snow_inches"])
        default_start = int(ps["start_hour"])
        default_duration = int(ps["duration_hours"])
        default_parking = float(ps["parking_compliance"])
        default_e = bool(ps["green_e_suspended"])
        default_view = int(active_preset["view_hour"])
    else:
        default_snow, default_start, default_duration = 14.0, 7, 10
        default_parking, default_e, default_view = 0.6, False, 8

    # When a preset is active its values drive the scenario directly; the sliders
    # are disabled so it's clear the preset is in charge (switch to Custom to edit).
    sliders_disabled = active_preset is not None

    snow_inches = st.sidebar.slider(
        "Snowfall (inches)",
        min_value=0.0,
        max_value=30.0,
        value=default_snow,
        step=0.5,
        help="Total storm snowfall, spread evenly over the duration.",
        disabled=sliders_disabled,
    )
    start_hour = st.sidebar.slider(
        "Start hour",
        min_value=0,
        max_value=23,
        value=default_start,
        step=1,
        help="Hour of day the snow begins (0-23).",
        disabled=sliders_disabled,
    )
    duration_hours = st.sidebar.slider(
        "Duration (hours)",
        min_value=1,
        max_value=24,
        value=default_duration,
        step=1,
        help="Length of the storm; snow is spread evenly over this window.",
        disabled=sliders_disabled,
    )
    hour_to_view = st.sidebar.slider(
        "Hour to view",
        min_value=0,
        max_value=23,
        value=default_view,
        step=1,
        help="Hour of day at which to evaluate conditions on the map.",
        disabled=sliders_disabled,
    )
    parking_compliance = st.sidebar.slider(
        "Cars moved off priority routes",
        min_value=0.0,
        max_value=1.0,
        value=default_parking,
        step=0.05,
        format="%.0f%%",
        help="Share of cars moved off snow-emergency routes. Lower compliance "
        "cuts priority-route capacity and plowing effectiveness.",
        disabled=sliders_disabled,
    )
    green_e_suspended = st.sidebar.checkbox(
        "Green Line E suspended",
        value=default_e,
        help="E branch down pushes more cars onto Huntington Avenue.",
        disabled=sliders_disabled,
    )

    # A disabled slider still returns its default, so whether a preset is active
    # or not, the variables above already hold the right values to build the
    # scenario from. (When disabled, they equal the preset; otherwise the user's.)

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
        # KPI cards always sit on top of the map, in both views (Requirement 15.3).
        render_kpi_cards(result)

        # Small scenario recap so the numbers always have context.
        recap = (
            f"{snow_inches:.1f} in of snow starting at {start_hour:02d}:00 over "
            f"{duration_hours} h - viewing {hour_to_view:02d}:00"
        )
        if green_e_suspended:
            recap += " - Green Line E suspended"
        st.caption(recap)

        # --- Map-mode toggle: hospital access vs breaking point --------------
        map_mode = st.radio(
            "Map view",
            options=["Hospital access", "Breaking point"],
            horizontal=True,
            help="Hospital access shows minutes to the nearest hospital at the "
            "chosen hour. Breaking point sweeps snowfall 0-30 in and colours "
            "each origin by how much snow it takes to cut it off.",
        )

        # The road graph is loaded once and cached (task 1.1 creates the
        # GraphML; until then the map renders origins only).
        graph = load_drive_graph()
        # Geometry is built once and cached; each slider move only recolours it.
        edge_geometry = load_edge_geometry(graph) if graph is not None else None

        if map_mode == "Hospital access":
            # --- Hospital-access map (Requirement 11.4) ----------------------
            st.subheader("Hospital access map")
            city_map = build_city_map(
                result,
                graph,
                edge_geometry=edge_geometry,
                max_origins=MAP_MAX_ORIGINS,
            )
            st_folium(city_map, width=800, height=500, returned_objects=[])

            if graph is None:
                st.caption(
                    "Road network not loaded yet — the GraphML cache is created "
                    "in task 1.1. Origin dots are shown from the simulation results."
                )
            st.caption(
                f"{len(result['origins'])} origins simulated · simulation estimate"
            )
        else:
            # --- Breaking-point map (Requirements 15.4, 15.3, 11.4) ----------
            st.subheader("Breaking-point map")
            st.caption(
                "Each origin is coloured by how much snow it takes to cut it off "
                "from every hospital (red = fragile, green = robust, grey = never "
                "breaks up to 30 in). Simulation estimate."
            )
            # The sweep is scenario-dependent but hour-independent (it sweeps
            # snowfall itself), so it's cached on the scenario contents.
            sweep_key = tuple(sorted(
                (k, tuple(v) if isinstance(v, list) else v)
                for k, v in scenario.items()
            ))
            sweep_result = run_sweep(sweep_key)
            origins_break = join_sweep_with_origins(sweep_result, result)

            break_map = build_breaking_point_map(
                origins_break,
                graph,
                edge_geometry=edge_geometry,
                max_origins=MAP_MAX_ORIGINS,
            )
            st_folium(break_map, width=800, height=500, returned_objects=[])

            # Honest, labelled summary (Requirement 7.4). "by X in" uses the
            # current snowfall slider so the number tracks the scenario on screen.
            summary_inches = float(snow_inches)
            n_break = count_broken_by(origins_break, summary_inches)
            n_never = sum(1 for o in origins_break if o["inches_to_break"] is None)
            if graph is None:
                st.caption(
                    "Road network not loaded yet — the GraphML cache is created "
                    "in task 1.1. Origin dots are shown from the sweep results."
                )
            st.caption(
                f"{n_break} of {len(origins_break)} origins break by "
                f"{summary_inches:.0f} in · {n_never} never break up to 30 in · "
                "simulation estimate"
            )

    with tab_trips:
        st.subheader("My trips")
        st.info(
            "Coming soon. This tab will run one persona's trip through the twin "
            "under live conditions and recommend when to leave and how to get there."
        )


if __name__ == "__main__":
    main()
