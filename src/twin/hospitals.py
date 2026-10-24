"""Hospitals for the study area. Owner: A.

Task 1.3: Get the 3 hospitals from OSM (amenity=hospital), snap each to a
sensible drive node, save data/cache/hospitals.json. (Requirement 15.1)

The three hospitals (Requirement 15): Beth Israel Deaconess, Brigham and
Women's, Boston Children's. We pull all amenity=hospital features in the bbox,
pick the feature whose name best matches each target, take a representative
point, and snap it to the nearest node of the cached drive graph.

Output shape (data/cache/hospitals.json):
    [
      {"key": "bidmc", "name": "<OSM name>", "lat": .., "lon": ..,
       "node": <drive-graph node id>},
      ...
    ]
B's multi-source Dijkstra reads the "node" ids; C labels markers with "name".

Depends on the cached drive graph from network.py. Build that first:
    python -m src.twin.network
    python -m src.twin.hospitals
"""
from __future__ import annotations

import json
from pathlib import Path

import osmnx as ox

from config.params import BBOX
from src.twin.network import CACHE_DIR, load_drive_graph

HOSPITALS_JSON = CACHE_DIR / "hospitals.json"

# Overpass (used by features_from_bbox) is often slow/rate-limited. Cache
# responses so retries are instant, and allow a generous read timeout so a
# slow-but-successful query isn't cut off. These settings are process-local.
try:
    ox.settings.use_cache = True
    ox.settings.requests_timeout = 180
    # Keep OSMnx's HTTP cache inside data/cache/ (gitignored) instead of the
    # default ./cache at the repo root.
    ox.settings.cache_folder = str(CACHE_DIR / "osmnx_http")
except Exception:  # pragma: no cover - older OSMnx without these settings
    pass

# Target hospitals: a stable key plus name fragments to match against OSM names.
# Matching is case-insensitive and substring-based; the first fragment that
# hits wins, so order fragments from most to least specific.
HOSPITAL_TARGETS = [
    {"key": "bidmc", "match": ["beth israel"]},
    {"key": "bwh", "match": ["brigham and women", "brigham & women", "brigham"]},
    {"key": "childrens", "match": ["boston children", "children's hospital", "children"]},
]


def _features_from_bbox(tags: dict):
    """Fetch OSM features in the bbox, tolerant of OSMnx v1/v2 signatures."""
    north = BBOX["north"]
    south = BBOX["south"]
    east = BBOX["east"]
    west = BBOX["west"]
    try:
        # v2: single bbox tuple (west, south, east, north)
        return ox.features_from_bbox(bbox=(west, south, east, north), tags=tags)
    except TypeError:
        pass
    # v1 features_from_bbox used north/south/east/west kwargs
    try:
        return ox.features_from_bbox(north=north, south=south, east=east, west=west, tags=tags)
    except (TypeError, AttributeError):
        # older OSMnx exposed geometries_from_bbox
        return ox.geometries_from_bbox(north, south, east, west, tags=tags)


def _representative_point(geom):
    """A single (lat, lon) for a hospital geometry (point or polygon)."""
    # Shapely geometry: use a guaranteed-interior point for polygons.
    pt = geom.representative_point() if geom.geom_type != "Point" else geom
    return float(pt.y), float(pt.x)  # (lat, lon)


def _match_hospital(name: str, targets_left: list[dict]) -> dict | None:
    low = (name or "").lower()
    for target in targets_left:
        if any(frag in low for frag in target["match"]):
            return target
    return None


def _nearest_node(G, lat: float, lon: float) -> int:
    # OSMnx nearest_node takes (G, X=lon, Y=lat).
    try:
        return int(ox.nearest_nodes(G, lon, lat))
    except AttributeError:
        # very old OSMnx
        return int(ox.distance.nearest_nodes(G, lon, lat))


def build_hospitals() -> list[dict]:
    """Find, match, and snap the three hospitals. Returns the records list."""
    G = load_drive_graph()

    print("Querying Overpass for amenity=hospital (may take up to a minute) ...",
          flush=True)
    gdf = _features_from_bbox({"amenity": "hospital"})
    print(f"Overpass returned {len(gdf)} hospital features.", flush=True)
    if "name" not in gdf.columns:
        raise RuntimeError("No named amenity=hospital features found in the bbox.")

    named = gdf[gdf["name"].notna()]

    results: dict[str, dict] = {}
    targets_left = list(HOSPITAL_TARGETS)

    for _idx, row in named.iterrows():
        if not targets_left:
            break
        target = _match_hospital(str(row["name"]), targets_left)
        if target is None:
            continue
        lat, lon = _representative_point(row.geometry)
        node = _nearest_node(G, lat, lon)
        results[target["key"]] = {
            "key": target["key"],
            "name": str(row["name"]),
            "lat": lat,
            "lon": lon,
            "node": node,
        }
        # Don't match this target again.
        targets_left = [t for t in targets_left if t["key"] != target["key"]]

    # Report any we couldn't find so A can hand-check on the map.
    found_keys = set(results.keys())
    missing = [t["key"] for t in HOSPITAL_TARGETS if t["key"] not in found_keys]
    if missing:
        print(f"WARNING: no OSM match for {missing}. "
              f"Check amenity=hospital names in the bbox or widen BBOX.")

    # Keep stable order matching HOSPITAL_TARGETS.
    return [results[t["key"]] for t in HOSPITAL_TARGETS if t["key"] in results]


def save_hospitals(records: list[dict], path: Path = HOSPITALS_JSON) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return path


def load_hospitals(path: Path = HOSPITALS_JSON) -> list[dict]:
    """Load cached hospital records; build them if missing."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    records = build_hospitals()
    save_hospitals(records, path)
    return records


def main() -> None:
    print("Finding hospitals (amenity=hospital) in the study-area bbox ...")
    records = build_hospitals()
    out = save_hospitals(records)
    print(f"Saved {len(records)} hospitals -> {out}")
    for r in records:
        print(f"  {r['key']:10s} node={r['node']:<12} "
              f"({r['lat']:.5f}, {r['lon']:.5f})  {r['name']}")
    if len(records) < 3:
        print("Fewer than 3 hospitals matched — hand-check names/bbox before the demo.")


if __name__ == "__main__":
    main()
