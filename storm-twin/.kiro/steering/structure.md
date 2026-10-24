---
inclusion: always
---

# Project structure

```
app.py                      Streamlit entry point (sliders + map, breaking-point mode, My trip)
config/params.py            every tunable number (owner D)
config/scenarios.py         the 3 demo scenarios (owner D)
src/contract.py             run_simulation / sweep_snow / trip_time: the only API the UI calls
mcp_server/server.py        boston-civic MCP server (MBTA + NWS tools)
src/
  twin/       model.py (Disruption, Scenario, Persona, Trip, Option)
              network.py (OSM drive/walk graphs, snow routes)
              transit.py (GTFS frequency graph, accessibility, elevators)
  scenarios/  storm.py (storm generator, presets), replay.py (snapshots)
  sim/        apply.py (Twin.with_scenario), planner.py, metrics.py, demo.py
  adapters/   mbta.py, nws.py, buoy.py, massdot.py (all external I/O lives here)
  personas/   synthetic.py (Census-based), onboarding.py
  history/    base_rates.py
  outputs/    ics.py, map.py, messages.py
  agent/      run.py (the agent loop)
  validation/ snow311.py
tests/        mirrors src/; fixtures/ holds recorded API responses
data/cache/   GraphML, GTFS zip, ACS pulls (gitignored)
data/snapshots/  timestamped live snapshots (replayable scenarios)
```

## Today
The UI and demo scripts import only `src/contract.py` and `config/`. See the file-ownership table in design.md.

## Dependency direction
`adapters` → produce `Disruption` / inputs → `scenarios` → `sim` → `outputs` → `agent`.
`twin` and `sim` never import `adapters`, `outputs` or `agent`.
