# Demo artifacts — three Storm Twin scenarios (task 12.2, owner D)

These files are evidence that all three demo presets run cleanly end to end
through the exact pipeline `app.py` uses, plus an openable map for each scenario
and map mode.

## How these were generated

`docs/demo/generate_artifacts.py` runs each preset in `config/scenarios.py`
through the same code path the Streamlit app uses:

1. `run_simulation(preset["scenario"], preset["view_hour"])` — the City-view call.
2. `sweep_snow(preset["scenario"])` — the Breaking-point call.
3. `build_city_map(...)` — hospital-access map (roads recoloured by capacity,
   origin dots by minutes to hospital).
4. `join_sweep_with_origins(...)` + `build_breaking_point_map(...)` — breaking-point
   map (origins coloured by how much snow it takes to cut them off).

Maps are built against the cached OSMnx drive graph in
`data/cache/drive.graphml` and saved with Folium's `Map.save(path)`. All three
scenarios ran with **no exceptions** over all 609 origins and ~1444 road edges.

Regenerate from the repo root with:

```
python docs/demo/generate_artifacts.py
```

## Screenshot limitation (read this)

Launching a live Streamlit server and taking real browser screenshots is not
possible in the headless build sandbox. **These saved HTML maps are the
screenshot substitute** — they are complete, standalone Leaflet/Folium pages.
Open any of them in a browser to screenshot it manually, or show it live.

To capture true in-app UI screenshots instead, run:

```
streamlit run app.py
```

then pick each preset from the sidebar dropdown, toggle **Hospital access** vs
**Breaking point**, and screenshot. The numbers and maps you see there match the
HTML files here because both go through the same contract functions.

## Artifacts

| Scenario | Hospital-access map | Breaking-point map |
|---|---|---|
| Regular heavy snow | `regular_heavy_snow_hospital.html` | `regular_heavy_snow_breaking_point.html` |
| Rush-hour blizzard | `rush_hour_blizzard_hospital.html` | `rush_hour_blizzard_breaking_point.html` |
| Blizzard + E branch suspended | `blizzard_e_suspended_hospital.html` | `blizzard_e_suspended_breaking_point.html` |

The machine-readable KPI table is in `scenario_kpis.json`.

## Headline KPIs

All numbers are **simulation estimates** (rule-based model outputs, not
measurements). 609 origins per scenario; 3 origins never break up to 30 in in
every scenario.

| Scenario | View hour | Origins broken | Avg min to hospital | Unreachable |
|---|---|---|---|---|
| Regular heavy snow | 13:00 | 2.0% | 3.1 min | 12 |
| Rush-hour blizzard | 08:00 | 2.0% | 5.4 min | 12 |
| Blizzard + E branch suspended | 08:00 | 2.0% | 5.5 min | 12 |

### How they compare

- **Average minutes to hospital** rises as conditions worsen: 3.1 → 5.4 → 5.5.
  The regular storm viewed mid-storm is easiest; the rush-hour blizzard viewed
  during the 7–9 peak nearly doubles the average trip; suspending the Green Line
  E branch pushes extra car volume onto Huntington Ave and adds a little more on
  top (5.4 → 5.5).
- **Origins broken (2.0%)** and **unreachable (12)** are the same across all
  three. Those 12 unreachable origins are structural — they have no route to any
  hospital under any of these scenarios — so the headline percentage doesn't move
  between presets; the story these presets tell is in the *average trip time*
  and in the breaking-point maps, not the broken count. The blizzard-vs-clear
  sanity target from task 8.2 (storm trips a few times a clear day, not 20×) holds.
