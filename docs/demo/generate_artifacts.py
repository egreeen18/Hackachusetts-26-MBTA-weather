"""Generate demo artifacts for all three Storm Twin scenarios (task 12.2, owner D).

Runs each of the three demo presets in ``config/scenarios.py`` through the exact
same code path ``app.py`` uses — ``run_simulation`` and ``sweep_snow`` from the
contract, then the hospital-access and breaking-point Folium maps from
``src/outputs/map.py`` — and saves each map as a standalone HTML file under
``docs/demo/``.

Headless browser screenshots are not available in the build sandbox, so these
saved HTML maps are the verifiable, openable substitute: open one in a browser to
screenshot it manually, or show it live during the demo.

This script is D-owned and self-contained. It only IMPORTS the frozen modules
(``src.contract``, ``src.outputs.map``, ``config.scenarios``, ``app``'s graph
loader is re-implemented locally so nothing in app.py is touched); it edits none
of them.

Run from the repo root:

    python docs/demo/generate_artifacts.py

It prints the headline KPIs per scenario and the artifact paths it wrote.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Make the repo root importable when run as ``python docs/demo/generate_artifacts.py``.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.scenarios import SCENARIOS  # noqa: E402
from src.contract import run_simulation, sweep_snow  # noqa: E402
from src.outputs.map import (  # noqa: E402
    build_breaking_point_map,
    build_city_map,
    join_sweep_with_origins,
    precompute_edge_geometry,
)

# Mirror app.py's constants so the artifacts match what the UI renders.
MAP_MAX_ORIGINS = 300
GRAPH_CACHE = REPO_ROOT / "data" / "cache" / "drive.graphml"
OUT_DIR = Path(__file__).resolve().parent


def load_drive_graph() -> Any:
    """Load the cached OSMnx drive graph (same cache file app.py uses).

    Returns the graph when the GraphML cache is present and loadable, else
    ``None`` so the maps still render origin dots (graceful degradation, exactly
    like app.py).
    """
    if not GRAPH_CACHE.exists():
        return None
    try:
        import osmnx as ox
        return ox.load_graphml(filepath=str(GRAPH_CACHE))
    except Exception as exc:  # pragma: no cover - reported, not raised
        print(f"  ! could not load drive graph: {exc!r} (maps will show dots only)")
        return None


def main() -> int:
    print(f"Repo root: {REPO_ROOT}")
    print(f"Output dir: {OUT_DIR}")
    graph = load_drive_graph()
    print(f"Drive graph: {'loaded' if graph is not None else 'NOT loaded (dots only)'}")
    edge_geometry = precompute_edge_geometry(graph) if graph is not None else None

    rows: list[dict] = []

    for key, preset in SCENARIOS.items():
        label = preset["label"]
        scenario = preset["scenario"]
        view_hour = preset["view_hour"]
        print(f"\n=== {label}  (key={key}, view_hour={view_hour}) ===")

        # 1) Hospital-access run — exactly app.py's City-view call.
        result = run_simulation(scenario, view_hour)
        kpis = result["kpis"]
        print(
            f"  run_simulation OK: {len(result['origins'])} origins, "
            f"{len(result['edges'])} edges"
        )

        # 2) Breaking-point sweep — exactly app.py's Breaking-point call.
        sweep_result = sweep_snow(scenario)
        origins_break = join_sweep_with_origins(sweep_result, result)
        n_never = sum(1 for o in origins_break if o["inches_to_break"] is None)
        print(f"  sweep_snow OK: {len(sweep_result)} nodes, {n_never} never break")

        # 3) Build both maps and save them as standalone HTML.
        hospital_map = build_city_map(
            result, graph, edge_geometry=edge_geometry, max_origins=MAP_MAX_ORIGINS
        )
        break_map = build_breaking_point_map(
            origins_break, graph, edge_geometry=edge_geometry, max_origins=MAP_MAX_ORIGINS
        )

        hospital_path = OUT_DIR / f"{key}_hospital.html"
        break_path = OUT_DIR / f"{key}_breaking_point.html"
        hospital_map.save(str(hospital_path))
        break_map.save(str(break_path))
        print(f"  saved {hospital_path.name}")
        print(f"  saved {break_path.name}")

        print(
            f"  KPIs: pct_broken={kpis['pct_broken']:.1f}%  "
            f"avg_min={kpis['avg_minutes_to_hospital']:.1f}  "
            f"n_unreachable={kpis['n_unreachable']}"
        )

        rows.append(
            {
                "key": key,
                "label": label,
                "view_hour": view_hour,
                "pct_broken": round(float(kpis["pct_broken"]), 1),
                "avg_minutes_to_hospital": round(
                    float(kpis["avg_minutes_to_hospital"]), 1
                ),
                "n_unreachable": int(kpis["n_unreachable"]),
                "n_origins": len(result["origins"]),
                "n_never_break": n_never,
                "hospital_html": hospital_path.name,
                "breaking_point_html": break_path.name,
            }
        )

    # Persist the KPI table next to the artifacts for the writeup/demo.
    kpi_path = OUT_DIR / "scenario_kpis.json"
    kpi_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\nWrote KPI summary: {kpi_path.name}")

    print("\nAll three scenarios ran end to end with no exceptions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
