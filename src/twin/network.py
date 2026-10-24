"""Road network for the study area. Owner: A.

Tasks:
  1.1  Download the drive network for the bbox in config/params.py with OSMnx,
       add free-flow speeds and travel times, save as GraphML in data/cache/.
       (Requirements 1.1, 1.3)
  1.2  Tag every edge with road_class: "priority" if its name matches
       PRIORITY_ROUTES (OSM names can be lists), else from ROAD_CLASS by
       highway tag. (Requirement 1.4)

This module touches only A-owned files (src/twin/*, data/cache/*). It never
imports from src/sim, app.py or src/outputs, so it cannot interfere with B/C/D.

Run once to build the cache:
    python -m src.twin.network
Then everyone else loads the cached graph via load_drive_graph().
"""
from __future__ import annotations

from pathlib import Path

import networkx as nx
import osmnx as ox

from config.params import BBOX, PRIORITY_ROUTES, ROAD_CLASS

# ---------------------------------------------------------------- paths

# repo layout: <root>/src/twin/network.py  ->  <root>
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
DRIVE_GRAPHML = CACHE_DIR / "drive.graphml"

# Default driving speed (km/h) OSMnx uses to fill edges whose highway type has
# no known maxspeed. Kept conservative for dense urban Longwood/Fenway streets.
DEFAULT_URBAN_SPEED_KPH = 40.0


# ---------------------------------------------------------------- bbox helper

def _graph_from_bbox():
    """Download the drive graph, tolerant of OSMnx v1 and v2 bbox signatures.

    v2 (Nov 2024+): graph_from_bbox(bbox=(west, south, east, north), ...)
    v1:             graph_from_bbox(north, south, east, west, ...)
    """
    north = BBOX["north"]
    south = BBOX["south"]
    east = BBOX["east"]
    west = BBOX["west"]

    # Prefer the v2 single-tuple form; fall back to the v1 keyword form.
    try:
        return ox.graph_from_bbox(
            bbox=(west, south, east, north),
            network_type="drive",
            truncate_by_edge=True,
        )
    except TypeError:
        return ox.graph_from_bbox(
            north=north,
            south=south,
            east=east,
            west=west,
            network_type="drive",
            truncate_by_edge=True,
        )


# ---------------------------------------------------------------- road_class (task 1.2)

# Normalize PRIORITY_ROUTES once for case-insensitive matching.
_PRIORITY_NAMES = {name.strip().lower() for name in PRIORITY_ROUTES}


def _edge_names(data: dict) -> list[str]:
    """Return an edge's street name(s) as a flat list of strings.

    OSM 'name' can be missing, a single string, or a list of strings
    (e.g. a segment that is part of two named ways).
    """
    name = data.get("name")
    if name is None:
        return []
    if isinstance(name, (list, tuple, set)):
        return [str(n) for n in name]
    return [str(name)]


def _highway_tags(data: dict) -> list[str]:
    """Return an edge's highway tag(s) as a flat list of strings."""
    hw = data.get("highway")
    if hw is None:
        return []
    if isinstance(hw, (list, tuple, set)):
        return [str(h) for h in hw]
    return [str(hw)]


def classify_edge(data: dict) -> str:
    """Return the road_class for one edge's attribute dict.

    Rule (design + task 1.2): any edge whose name matches a PRIORITY_ROUTES
    entry is "priority" regardless of highway tag; otherwise map the highway
    tag through ROAD_CLASS; unknown highway tags default to "side".
    """
    for n in _edge_names(data):
        if n.strip().lower() in _PRIORITY_NAMES:
            return "priority"

    # If the edge carries several highway tags, prefer the most important
    # class present (priority already handled above, so main beats side).
    classes = {ROAD_CLASS.get(h, "side") for h in _highway_tags(data)}
    if not classes:
        return "side"
    if "main" in classes:
        return "main"
    return "side"


def tag_road_classes(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Add a 'road_class' attribute to every edge in place; returns G."""
    for _u, _v, data in G.edges(data=True):
        data["road_class"] = classify_edge(data)
    return G


# ---------------------------------------------------------------- build (task 1.1)

def build_drive_graph() -> nx.MultiDiGraph:
    """Download the drive graph, add speeds + travel times, tag road_class."""
    G = _graph_from_bbox()

    # Free-flow speeds (km/h) and travel times (seconds). add_edge_speeds fills
    # 'speed_kph' from OSM maxspeed where present, imputing by highway type
    # otherwise; add_edge_travel_times derives 'travel_time' = length / speed.
    G = ox.add_edge_speeds(G, fallback=DEFAULT_URBAN_SPEED_KPH)
    G = ox.add_edge_travel_times(G)

    G = tag_road_classes(G)
    return G


def save_drive_graph(G: nx.MultiDiGraph, path: Path = DRIVE_GRAPHML) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(G, str(path))
    return path


def load_drive_graph(path: Path = DRIVE_GRAPHML) -> nx.MultiDiGraph:
    """Load the cached drive graph. Build and cache it if missing.

    This is the function C and B call. GraphML stores attributes as strings,
    so OSMnx re-types the numeric ones on load; road_class stays a string.
    """
    if path.exists():
        return ox.load_graphml(str(path))
    G = build_drive_graph()
    save_drive_graph(G, path)
    return G


# ---------------------------------------------------------------- CLI

def main() -> None:
    print(f"Study-area bbox: {BBOX}")
    print("Downloading drive network from OpenStreetMap ...")
    G = build_drive_graph()

    out = save_drive_graph(G)

    # Summary / self-check.
    n_nodes = G.number_of_nodes()
    n_edges = G.number_of_edges()
    class_counts: dict[str, int] = {}
    missing_tt = 0
    for _u, _v, data in G.edges(data=True):
        class_counts[data.get("road_class", "?")] = (
            class_counts.get(data.get("road_class", "?"), 0) + 1
        )
        if "travel_time" not in data or "speed_kph" not in data:
            missing_tt += 1

    print(f"Saved GraphML -> {out}")
    print(f"Nodes: {n_nodes}  Edges: {n_edges}")
    print(f"road_class counts: {class_counts}")
    if missing_tt:
        print(f"WARNING: {missing_tt} edges missing speed_kph/travel_time")
    else:
        print("All edges have speed_kph and travel_time.")


if __name__ == "__main__":
    main()
