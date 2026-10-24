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

import json
from datetime import date, datetime, time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import streamlit as st
from streamlit_folium import st_folium

from config.scenarios import SCENARIOS
from src.adapters.live import live_scenario  # task 15: "Live now" button (A)
from src.contract import Scenario, SimResult, run_simulation, sweep_snow, trip_time
from src.outputs.ics import build_trip_ics, compute_leave_by
from src.outputs.map import (
    build_breaking_point_map,
    build_city_map,
    build_trip_map,
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

# A-owned hospitals cache (read-only here): the three Longwood hospitals with
# snapped nodes and lat/lon. Used to offer destinations (and a couple of "home"
# presets) in the My-trips form.
HOSPITALS_CACHE = Path(__file__).resolve().parent / "data" / "cache" / "hospitals.json"

# A few demo-friendly "home" points inside the study area (lat, lon). These are
# synthetic study-area locations, NOT anyone's real address (Requirement 13.2).
# Keeps the persona form one-click for a demo while still allowing custom lat/lon.
PRESET_HOME_POINTS: dict[str, tuple[float, float]] = {
    "Fenway (near Green Line D)": (42.3457, -71.1041),
    "Mission Hill": (42.3330, -71.1010),
    "Longwood edge (Brookline Ave)": (42.3440, -71.1010),
    "Northeastern / Ruggles": (42.3365, -71.0893),
}

# Safety buffer presets for the "Leave by" computation (minutes). The design
# notes critical trips warrant +20 min, important +10 (Requirements 6.1/6.2);
# we expose that as a simple, documented cushion on top of the storm travel time.
TRIP_BUFFER_CHOICES: dict[str, int] = {
    "None (just travel time)": 0,
    "Important (+10 min)": 10,
    "Critical (+20 min)": 20,
}


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


@st.cache_data
def load_hospitals_for_trips() -> list[dict]:
    """Read the A-owned hospitals cache (read-only) for the trip form.

    Returns a list of ``{"key", "name", "lat", "lon"}`` dicts, or an empty list
    if the cache isn't present yet (the form then falls back to lat/lon inputs).
    We never write this file — it's A's; we only read the labels and coordinates
    to offer as trip destinations and a couple of "home" presets.
    """
    if not HOSPITALS_CACHE.exists():
        return []
    try:
        with HOSPITALS_CACHE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return [
            {
                "key": h.get("key"),
                "name": h.get("name"),
                "lat": float(h["lat"]),
                "lon": float(h["lon"]),
            }
            for h in data
            if "lat" in h and "lon" in h
        ]
    except Exception:
        return []


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


# --------------------------------------------------------------------------- my-trips tab


def _latlon_picker(
    role: str,
    place_options: dict[str, tuple[float, float]],
    default_latlon: tuple[float, float],
) -> tuple[str, tuple[float, float]]:
    """Render a place picker + custom lat/lon inputs for one trip end.

    ``role`` is "home" or "destination" (used to key the widgets and label).
    ``place_options`` maps a place label to its ``(lat, lon)``. The user picks a
    named place or chooses "Custom lat/lon…" and types coordinates. Returns the
    chosen ``(label, (lat, lon))``.

    Privacy (Requirement 4.3/13): this only ever collects a place *label* and a
    location — there is deliberately no field for a reason, diagnosis or address.
    """
    custom_label = "Custom lat/lon…"
    options = list(place_options.keys()) + [custom_label]
    choice = st.selectbox(
        f"{role.capitalize()} location",
        options=options,
        key=f"trip_{role}_place",
        help=f"Pick a {role} location in the study area, or enter coordinates.",
    )
    if choice == custom_label:
        col_a, col_b = st.columns(2)
        lat = col_a.number_input(
            f"{role.capitalize()} latitude",
            value=float(default_latlon[0]),
            format="%.5f",
            key=f"trip_{role}_lat",
        )
        lon = col_b.number_input(
            f"{role.capitalize()} longitude",
            value=float(default_latlon[1]),
            format="%.5f",
            key=f"trip_{role}_lon",
        )
        return f"Custom ({lat:.4f}, {lon:.4f})", (float(lat), float(lon))
    return choice, place_options[choice]


def render_trips_tab(scenario: Scenario, hour_to_view: int, graph: Any,
                     edge_geometry: Any, live_meta: Any) -> None:
    """Render the "My trips" tab: persona form, trip result, map and .ics.

    Task 17 (Requirements 4.1, 4.3, 11.1, 11.2). Collects a synthetic persona's
    home, destination, arrive-by time and a "needs step-free" flag; runs
    ``trip_time`` under the current City-view scenario; shows storm vs clear-day
    minutes, the broken flag and any warnings; draws the route on a map; computes
    a "Leave by" time; and offers an .ics download.

    Privacy (Requirement 4.3/13): no medical-reason field exists, and nothing
    here is logged.
    """
    st.subheader("My trip")
    st.caption(
        "A synthetic persona's trip through the twin under the current scenario. "
        "We store a place label and location only — never why you're going "
        "(no medical reason, no diagnosis, no address). Nothing here is logged."
    )

    hospitals = load_hospitals_for_trips()

    # Destination options: the three hospitals (demo-friendly), plus the preset
    # home points so a user can also route between two study-area points.
    dest_options: dict[str, tuple[float, float]] = {}
    for h in hospitals:
        dest_options[h["name"]] = (h["lat"], h["lon"])
    dest_options.update(PRESET_HOME_POINTS)

    # Home options: the preset study-area points, plus hospitals (someone may
    # live near one). All synthetic — no real addresses.
    home_options: dict[str, tuple[float, float]] = dict(PRESET_HOME_POINTS)
    for h in hospitals:
        home_options[h["name"]] = (h["lat"], h["lon"])

    default_home = next(iter(PRESET_HOME_POINTS.values()))
    default_dest = (hospitals[0]["lat"], hospitals[0]["lon"]) if hospitals else \
        next(iter(PRESET_HOME_POINTS.values()))

    # --- The persona / trip form (Requirement 4.1, 4.3) ----------------------
    with st.form("my_trip_form"):
        home_label, home_latlon = _latlon_picker("home", home_options, default_home)
        dest_label, dest_latlon = _latlon_picker(
            "destination", dest_options, default_dest
        )

        col_time, col_buf = st.columns(2)
        arrive_by_t = col_time.time_input(
            "Arrive by",
            value=time(9, 0),
            help="The time you need to arrive at your destination.",
        )
        buffer_label = col_buf.selectbox(
            "Safety buffer",
            options=list(TRIP_BUFFER_CHOICES.keys()),
            index=1,
            help="Extra cushion added before the travel time when picking a "
            "leave-by time. Critical trips warrant more.",
        )

        needs_step_free = st.checkbox(
            "Needs step-free access",
            value=False,
            help="Flag elevator outages on the route's transit stops.",
        )

        # Deliberately NO reason / why / diagnosis field here (Requirement 4.3).
        submitted = st.form_submit_button("Plan my trip")

    if not submitted:
        st.info("Fill in the trip above and press **Plan my trip**.")
        return

    # --- Run the trip through the contract (Requirement 16.3) ----------------
    trip = trip_time(home_latlon, dest_latlon, scenario, hour_to_view)
    storm_minutes = trip["minutes"]
    clear_minutes = trip["clear_day_minutes"]
    routable = storm_minutes == storm_minutes and storm_minutes != float("inf")

    # Result metrics.
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Storm trip",
        "no route" if not routable else f"{storm_minutes:.0f} min",
        help="Travel time from home to destination under the current scenario.",
    )
    c2.metric(
        "Clear-day trip",
        "—" if clear_minutes == float("inf") else f"{clear_minutes:.0f} min",
        help="The same trip on a clear day (free-flow reference).",
    )
    c3.metric(
        "Leave earlier by",
        f"{trip['leave_earlier_by_min']:.0f} min",
        help="How much earlier to leave than on a clear day.",
    )

    if trip["broken"]:
        st.error(
            "This trip is **broken** — over 30 minutes or no route at all under "
            "this scenario. Consider rescheduling or a fallback option."
        )

    # Warnings (e.g. elevator outages). Surface them prominently when the
    # persona needs step-free access.
    if trip["warnings"]:
        if needs_step_free:
            st.warning(
                "Step-free access needed — watch these: "
                + "; ".join(trip["warnings"])
            )
        else:
            st.info("Heads-up: " + "; ".join(trip["warnings"]))
    elif needs_step_free:
        st.caption("No elevator outages reported on this scenario's stops.")

    # --- "Leave by" time + .ics (Requirement 11.1) ---------------------------
    safety_buffer = TRIP_BUFFER_CHOICES[buffer_label]
    arrive_by_dt = datetime.combine(date.today(), arrive_by_t)

    if routable:
        leave_by_dt = compute_leave_by(arrive_by_dt, storm_minutes, safety_buffer)
        st.success(
            f"**Leave by {leave_by_dt.strftime('%H:%M')}** to arrive by "
            f"{arrive_by_dt.strftime('%H:%M')} "
            f"({storm_minutes:.0f} min travel + {safety_buffer} min buffer). "
            "Simulation estimate."
        )

        summary = (
            f"Storm trip {storm_minutes:.0f} min vs {clear_minutes:.0f} min clear "
            f"day; buffer {safety_buffer} min."
            if clear_minutes != float("inf")
            else f"Storm trip {storm_minutes:.0f} min; buffer {safety_buffer} min."
        )
        ics_bytes = build_trip_ics(
            trip_label=dest_label,
            leave_by_dt=leave_by_dt,
            arrive_by_dt=arrive_by_dt,
            summary=summary,
        )
        st.download_button(
            "⬇️ Download .ics (Leave by + travel block)",
            data=ics_bytes,
            file_name="storm_twin_trip.ics",
            mime="text/calendar",
            help="Adds a 'Leave by' reminder and a travel block to your calendar.",
        )
    else:
        st.warning(
            "No route under this scenario, so there's no leave-by time to add to "
            "a calendar. The map below shows just home and destination."
        )

    # --- Route on the map (Requirements 11.1, 11.2) --------------------------
    st.subheader("Trip route")
    trip_map = build_trip_map(
        route_nodes=trip["route_nodes"],
        graph=graph,
        home_latlon=home_latlon,
        dest_latlon=dest_latlon,
        broken=trip["broken"],
        minutes=storm_minutes,
        edge_geometry=edge_geometry,
    )
    st_folium(trip_map, width=800, height=500, returned_objects=[])

    if graph is None:
        st.caption(
            "Road network not loaded yet — the GraphML cache is created in task "
            "1.1. Showing home and destination markers only."
        )
    st.caption("Route and times are a simulation estimate.")


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

    # --- "Live now" button (task 15, Requirements 8.4/8.5) -------------------
    # Pulls current NWS snow + MBTA E-suspension/elevator flags via the A-owned
    # aggregator and runs the simulator on them instead of the sliders/preset.
    # The result is stashed in session_state so it survives the rerun a slider
    # change triggers; "Use sliders/preset" clears it.
    st.sidebar.markdown("---")
    if st.sidebar.button("🔴 Live now", help="Fetch current NWS weather and MBTA "
                         "alerts and simulate conditions right now."):
        st.session_state["live"] = live_scenario()  # (scenario, meta)
    live_active = "live" in st.session_state
    if live_active and st.sidebar.button("Use sliders / preset instead"):
        del st.session_state["live"]
        live_active = False

    # --- Build the scenario and run the simulator ----------------------------
    if live_active:
        scenario, live_meta = st.session_state["live"]
        hour_to_view = int(live_meta["view_hour"])
    else:
        live_meta = None
        scenario = build_scenario(
            snow_inches=snow_inches,
            start_hour=start_hour,
            duration_hours=duration_hours,
            parking_compliance=parking_compliance,
            green_e_suspended=green_e_suspended,
        )

    # The contract is the only API the UI is allowed to call (Requirement 16.1).
    result: SimResult = run_simulation(scenario, hour_to_view)

    # The road graph is loaded once and cached (task 1.1 creates the GraphML;
    # until then the maps render without road edges). Both tabs share it, so it
    # is loaded here before the tabs rather than inside the City view.
    graph = load_drive_graph()
    # Geometry is built once and cached; each slider move only recolours it.
    edge_geometry = load_edge_geometry(graph) if graph is not None else None

    # --- Two tabs (per design.md) --------------------------------------------
    tab_city, tab_trips = st.tabs(["City view", "My trips"])

    with tab_city:
        # KPI cards always sit on top of the map, in both views (Requirement 15.3).
        render_kpi_cards(result)

        # Small scenario recap so the numbers always have context. When "Live now"
        # is active the recap comes from the live scenario and carries a freshness
        # label (Requirement 8.4).
        if live_meta is not None:
            recap = (
                f"Live: {scenario['snow_inches']:.1f} in of snow starting at "
                f"{scenario['start_hour']:02d}:00 over "
                f"{scenario['duration_hours']} h - viewing {hour_to_view:02d}:00"
            )
            if scenario["green_e_suspended"]:
                recap += " - Green Line E suspended"
            st.caption(recap)

            if live_meta["no_live_data"]:
                st.warning(
                    "No live data available right now (no connection and no saved "
                    "snapshot). Showing a calm no-storm baseline — switch to the "
                    "sliders or a preset to explore scenarios."
                )
            elif live_meta["any_stale"]:
                st.warning(
                    f"Based on stale data (as of {live_meta['data_as_of_hhmm']}). "
                    "A live source was unavailable, so the last saved snapshot is "
                    "shown."
                )
            else:
                st.caption(f"Data as of {live_meta['data_as_of_hhmm']}")
        else:
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

        # graph + edge_geometry were loaded above (shared by both tabs).
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
        render_trips_tab(
            scenario=scenario,
            hour_to_view=hour_to_view,
            graph=graph,
            edge_geometry=edge_geometry,
            live_meta=live_meta,
        )


if __name__ == "__main__":
    main()
