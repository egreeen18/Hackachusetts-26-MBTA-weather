---
name: add-data-adapter
description: Add a new external data source to Storm Twin as an adapter that produces Disruptions or storm inputs. Use when connecting a new API or dataset (for example MassDOT work zones, a new MBTA endpoint, or another city's open data).
---

# Adding a data adapter

Storm Twin keeps the simulator pure. A new source never changes `src/sim/` or `src/twin/`; it only produces objects the simulator already understands.

## Steps
1. Decide what the source becomes. Exactly one of:
   - part of the base twin (static, loaded once) → add to `src/twin/`
   - `Disruption`s (changes over time) → new file in `src/adapters/`
   - `StormInputs` (weather) → `src/adapters/`, fed into `generate_storm`
   - persona attributes → `src/personas/`
2. Record one real response into `tests/fixtures/<source>_<endpoint>.json` before writing parsing code. Use the boston-civic MCP server or a one-off script.
3. Write `fetch_<source>(now) -> tuple[list[Disruption], datetime]`:
   - `httpx` with a 10 s timeout
   - filter to the study-area bbox
   - map each record to a `DisruptionKind`; put plain-language text in `reason`
   - on any failure, return the last snapshot and set `stale_since`; never raise
4. Write tests against the fixture: counts, kinds, targets inside the bbox, and the failure path.
5. Add the source to the table in `design.md` and to `.kiro/steering/data-sources.md`.
6. Add it to `live_scenario()` in `src/scenarios/` and to the snapshot writer.

## Checklist
- [ ] No import of `src/adapters` from `src/sim` or `src/twin`
- [ ] Secrets only from environment variables
- [ ] Logs show endpoint and counts only
- [ ] Fixture committed, live calls absent from tests
