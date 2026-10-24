# Implementation Plan: today, Saturday Oct 24 (deadline 6pm, buffer to 7pm)

**Principle:** get one scenario running end to end first, then add features. If a checkpoint is missed, cut features immediately; don't push through.

**Owners:** A = Road network & data · B = Simulation logic · C = UI & map · D = Aurora, parameters & demo. Whoever has used OSMnx or GeoPandas takes A.

**Everyone codes against `src/contract.py`.** Its stub already returns fake but correctly shaped data, so C can build the UI from minute one while B builds the real simulator.

| Clock | Block | Checkpoint (must be true to continue) |
|---|---|---|
| 12:00–12:20 | Kickoff (everyone) | Contract agreed, repo runs, Kiro set up |
| 12:20–1:15 | Block 1 | **CP1 1:15:** road network renders on the map |
| 1:15–2:30 | Block 2 (eat at desks) | **CP2 2:30:** moving the snowfall slider recolors the map |
| 2:30–3:30 | Block 3 | **CP3 3:30:** breaking-point map works |
| 3:30–4:00 | MVP freeze (everyone) | Tagged `mvp`, backup video #1 recorded |
| 4:00–5:00 | Block 4: extensions | **CP4 5:00:** live conditions + one persona's trip |
| 5:00–5:30 | Integration (everyone) | **Code freeze 5:30** |
| 5:30–6:00 | Rehearse + submit (everyone) | Final video, repo pushed with `.kiro/` |
| 6:00–7:00 | Buffer / presenting | |

---

## Kickoff, 12:00–12:20 (everyone)

- [ ] 0.1 [All] Read `src/contract.py` together and agree on it; do not change return shapes later without telling everyone
  - _Requirements: 16.1, 16.2_
- [ ] 0.2 [All] Clone repo, `pip install osmnx networkx geopandas streamlit streamlit-folium folium httpx icalendar hypothesis pytest mcp`; open in Kiro and check steering, hooks and the `boston-civic` MCP server load
- [ ] 0.3 [All] Git rule: each person edits only their own files (see design.md "File ownership"); merge to `main` at every checkpoint

---

## Block 1, 12:20–1:15 → CP1: road network renders on the map

- [ ] 1. [A] Road network
  - [ ] 1.1 [A] Download the drive network for the bbox in `config/params.py` with OSMnx; add free-flow speeds and travel times; save as GraphML in `data/cache/`
    - _Requirements: 1.1, 1.3_
  - [ ] 1.2 [A] Tag every edge with `road_class`: "priority" if its name matches `PRIORITY_ROUTES` (OSM names can be lists), else from `ROAD_CLASS` by highway tag
    - _Requirements: 1.4_
  - [ ] 1.3 [A] Get the 3 hospitals from OSM (`amenity=hospital`), snap each to a sensible drive node, save `data/cache/hospitals.json`
    - _Requirements: 15.1_
- [x] 2. [B] Snow and plowing rules (pure functions, dummy data)
  - [x] 2.1 [B] `snow_on_road(road_class, scenario, hour)`: even accumulation over the storm, plow schedule per class, side streets cleared after the storm ends
    - _Requirements: 3.1, 3.2_
  - [x] 2.2 [B] `capacity_factor(snow_in, road_class)`: interpolate `CAPACITY_TABLE`; side streets ≥ 12 in → 0 (impassable)
    - _Requirements: 3.4, 3.7_
  - [x] 2.3 [B] Tests, including property tests: more snow never lowers snow-on-road; 0 in gives factor 1.0
    - _Requirements: 3.6, 3.7_
- [ ] 3. [C] Streamlit shell
  - [ ] 3.1 [C] `app.py`: sliders for snowfall (0–30), start hour, duration, hour to view, parking compliance, E suspended toggle; build the scenario dict; call the stub `run_simulation`
    - _Requirements: 16.1_
  - [ ] 3.2 [C] Folium map of the bbox via `streamlit-folium`; KPI card placeholders; once A's GraphML exists, draw edges (load with `st.cache_resource`)
    - _Requirements: 11.4_
- [ ] 4. [D] Parameters and setup
  - [ ] 4.1 [D] Own `config/params.py` (defaults already drafted): read every number, adjust anything that looks wrong, keep `simulation-assumptions.md` in sync
    - _Requirements: 3.1_
  - [ ] 4.2 [D] Confirm Kiro hooks fire (edit a test file) and the MCP server answers `mbta_alerts`; save one MBTA and one NWS response to `tests/fixtures/`
    - _Requirements: 8.1, 8.3_
  - [ ] 4.3 [D] Start the writeup: problem, who it serves, what the twin shows

**CP1 (1:15):** the real Longwood + Fenway road network is on the map. If A is stuck on OSMnx, everyone helps A; nothing else matters yet.

---

## Block 2, 1:15–2:30 → CP2: moving the snowfall slider recolors the map

- [ ] 5. [A] MBTA data
  - [ ] 5.1 [A] Green Line D and E stops in the bbox with wheelchair accessibility and elevator facility ids
    - _Requirements: 1.5_
  - [ ] 5.2 [A] `mbta_flags()` → `{"green_e_suspended": bool, "elevators_out": [...]}` from live alerts (SUSPENSION/SHUTTLE on Green-E; ELEVATOR_CLOSURE at study-area stops); test against saved fixtures
    - _Requirements: 8.1, 8.2_
- [ ] 6. [B] Real `run_simulation`
  - [ ] 6.1 [B] Capacity with parked cars on priority routes; volume from `BASE_VC` × demand drop; E suspension adds v/c on Huntington edges
    - _Requirements: 3.3, 3.5_
  - [ ] 6.2 [B] Edge travel time = free-flow / cap^0.5 × BPR(min(v/c, cap)); impassable edges removed
    - _Requirements: 3.4_
  - [ ] 6.3 [B] Minutes to nearest hospital for every origin with one multi-source Dijkstra on the reversed graph; broken flag; KPIs; replace the stub in `src/contract.py`
    - _Requirements: 15.1, 15.2, 15.3, 16.1, 7.4_
  - [ ] 6.4 [B] Property test: more snow or lower compliance never makes any origin closer
    - _Requirements: 3.6_
- [ ] 7. [C] Map coloring
  - [ ] 7.1 [C] Roads colored by capacity factor (green → red, closed = black); origin dots by minutes (≤15, 15–30, >30, unreachable); legend
    - _Requirements: 11.4_
  - [ ] 7.2 [C] Keep it fast: build geometry once, only recolor on slider change; sample origins for display if slow
- [ ] 8. [D] Scenarios and sanity checks
  - [ ] 8.1 [D] `config/scenarios.py`: regular heavy snow, rush-hour blizzard, blizzard + E branch suspended
    - _Requirements: 3.8_
  - [ ] 8.2 [D] As soon as B's real `run_simulation` lands, run all three and check: blizzard hospital trips 2–4× clear day, not 20×; tune `SPEED_EXPONENT` / `VC_CAP` if needed; note headline numbers

**CP2 (2:30):** dragging the snowfall slider visibly changes road colors and KPIs using the real simulator.

---

## Block 3, 2:30–3:30 → CP3: breaking-point map works

- [ ] 9. [A] Optional data layers (only if CP2 was on time; otherwise help C)
  - [ ] 9.1 [A] (optional) 311 snow/plow complaints in the bbox for a past Boston blizzard from Analyze Boston, as a validation layer
    - _Requirements: 14.1_
  - [ ] 9.2 [A] NWS adapter: forecast snowfall and timing → `snow_inches`, `start_hour`, `duration_hours`
    - _Requirements: 8.3_
- [ ] 10. [B] Sweep and trip time
  - [ ] 10.1 [B] `sweep_snow(scenario)`: 0 → 30 in by 2 in (16 runs), first breaking level per origin
    - _Requirements: 15.4_
  - [ ] 10.2 [B] `trip_time(origin, dest, scenario, hour)`: storm vs clear-day minutes, broken, leave-earlier, route nodes, elevator warnings
    - _Requirements: 16.3_
- [ ] 11. [C] Breaking-point mode
  - [ ] 11.1 [C] Toggle to the breaking-point map (origins colored by inches to break; "never" in gray); KPI cards on top; scenario preset dropdown from D's file
    - _Requirements: 15.3, 15.4, 11.4_
- [ ] 12. [D] Demo script
  - [ ] 12.1 [D] 3-minute script: clear → rush-hour blizzard → + E suspended → breaking-point map; say the numbers are assumptions
    - _Requirements: 7.4_
  - [ ] 12.2 [D] Run all three scenarios end to end in the UI; screenshot each

**CP3 (3:30):** breaking-point map works. **If not, skip Block 4 entirely; everyone fixes the MVP.**

---

## MVP freeze, 3:30–4:00 (everyone)

- [ ] 13. [All] Merge, fix bugs, run the full demo once, `git tag mvp`
- [ ] 14. [D] Record backup video #1 of the MVP demo

---

## Block 4, 4:00–5:00 → CP4: live conditions + one persona's trip

- [ ] 15. [A] "Live now" button: NWS → snow fields, MBTA → E suspension + elevators out; on failure use the last saved snapshot and show "data as of HH:MM"
  - _Requirements: 8.4, 8.5_
- [ ] 16. [B] `trip_time` polish + property test (more snow never makes a trip faster); clear-day vs storm comparison for "time to leave earlier"
  - _Requirements: 16.3, 3.6_
- [ ] 17. [C] "My trip" tab: synthetic persona form (home, destination, arrive-by, needs step-free), route on map, "Leave by" time, .ics download
  - _Requirements: 4.1, 4.3, 11.1, 11.2_
- [ ] 18. [D] Message (≤ 320 chars, plain language, leave-by time) + test; 3 synthetic personas in `tests/fixtures/`; run the accessibility-reviewer agent; finish the Kiro section of the writeup
  - _Requirements: 11.3, 13.2, 13.3_

**CP4 (5:00):** if not working, drop it from the demo and present it as the next step.

---

## Integration and submit

- [ ] 19. [All] 5:00–5:30 merge, fix, full run-through. **Code freeze at 5:30.**
- [ ] 20. [All] 5:30–6:00 rehearse twice, record final video (D), push repo with `.kiro/` committed, submit writeup

---

## Cut order if behind

1. 311 validation layer (9.1)
2. Elevator alerts (part of 5.2)
3. E branch suspension effect on traffic (part of 6.1)
4. All of Block 4

**Fallback that still tells the full story:** snowfall + plowing only, plus the breaking-point map.

## Not today
Full transit planner, rideshare costs, sustainability ranking, seasonal patterns, Census synthetic personas (Requirements 5, 6, 9, 10, 12, 4.4, 7.3).
