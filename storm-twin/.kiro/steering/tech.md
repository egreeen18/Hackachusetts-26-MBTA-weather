---
inclusion: always
---

# Technology

- Python 3.11+. Type hints everywhere; dataclasses for the data model.
- Graphs: `osmnx` for OpenStreetMap street networks, `networkx` for routing.
- Tables and geo: `pandas`, `geopandas`.
- HTTP: `httpx` with explicit timeouts (10 s). Every external call goes through an adapter in `src/adapters/`.
- App: `streamlit` with two tabs (City view, My trips). Maps with `folium` (or `pydeck` if needed for the tract choropleth).
- Calendar: `icalendar`.
- Tests: `pytest` + `hypothesis` for property tests. Never call live APIs in tests; use `tests/fixtures/`.
- LLM: used only to polish messages and for optional conversational onboarding. Never to choose routes or compute numbers.
- MCP: the project's own `boston-civic` server (`mcp_server/server.py`) wraps MBTA and NWS for use inside Kiro during development.

## Rules
- Keep the simulator pure: `src/sim/` and `src/twin/` must not import from `src/adapters/`.
- Randomness is seeded (`random.Random(seed)`) so scenarios are reproducible.
- Cache anything slow to fetch in `data/cache/`; the demo must run offline from cache.
- Secrets come from environment variables (`MBTA_API_KEY`), never from code or steering.
