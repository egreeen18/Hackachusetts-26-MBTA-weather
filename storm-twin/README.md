# Storm Twin: Longwood + Fenway

A digital twin of the Longwood Medical Area and Fenway that simulates storms and transit disruptions, plus a personal agent that keeps vulnerable residents' critical trips on track.

The full spec lives in `.kiro/specs/longwood-storm-twin/` (requirements → design → tasks). **Build the simulator first** (Phase 1 in tasks.md); everything else plugs into it.

## Getting started in Kiro

1. Open this folder in Kiro. The steering files, hooks, MCP server, custom agent and skill load automatically from `.kiro/`.
2. Set environment variables, then approve them when Kiro asks (Settings → "Mcp Approved Env Vars"):
   - `MBTA_API_KEY` (free from api-v3.mbta.com)
   - `NWS_USER_AGENT`, e.g. `StormTwin (your-team-email)`
3. `pip install mcp httpx` so the `boston-civic` MCP server can start; check it shows as connected in the MCP panel.
4. Open `tasks.md` and run Phase 0 and Phase 1 tasks. Kiro groups independent tasks into parallel waves when you run them all.

## How each Kiro feature is used (for the writeup)

| Kiro feature | File(s) | What it does for this project |
|---|---|---|
| **Spec** | `.kiro/specs/longwood-storm-twin/` | 14 requirements in EARS notation; every task traces to requirement numbers. Accessibility, budget and privacy promises are written as testable acceptance criteria. |
| **Correctness** (property-based tests) | tests from tasks 4.3, 5.3, 6.6 | Proves storm monotonicity, baseline restore after a scenario, and "a step-free persona is never routed through a broken elevator". |
| **Steering, always** | `product.md`, `tech.md`, `structure.md`, `privacy-and-messages.md` | Who we serve, the stack, the dependency direction (simulator never imports adapters), privacy and plain-language rules. |
| **Steering, fileMatch** | `simulation-assumptions.md`, `data-sources.md` | Model coefficients load only when editing simulator code; API conventions load only when editing adapters. |
| **Hooks** | `.kiro/hooks/*.json` | Tests on every simulator edit and after every spec task; an agent hook keeps the assumptions file in sync with code constants; a message checker; a privacy guard before every write. |
| **MCP** | `.kiro/settings/mcp.json`, `mcp_server/server.py` | Our own server wraps MBTA and NWS so Kiro can look at real alerts and forecasts while writing parsers, and the product agent reuses the same tools. |
| **Custom agent** | `.kiro/agents/accessibility-reviewer.json` | A reviewer that runs the blizzard demo and audits recommendations against requirements 5, 6, 10, 12 and 13. Invoke it as a sub-agent after planner changes. |
| **Skill** | `.kiro/skills/add-data-adapter/` | Repeatable recipe for plugging in a new data source without touching the simulator. Use `/add-data-adapter` for MassDOT work zones. |

Things to verify in your Kiro version: hook trigger names (this repo uses `PostFileSave`, `PostTaskExecution`, `PreToolUse`); if one doesn't load, recreate it with "Ask Kiro to create a hook" using the description field. Also check that the custom agent appears in the agent picker.

## Demo flow (about 3 minutes)

1. **City view, Clear → Blizzard.** Tract map of hospital reachability for car-free seniors changes; read the headline number. Toggle snow emergency routes on.
2. **My trips.** Synthetic persona, 78, lives alone, step-free, $15 ride budget, 10:00 pharmacy pickup at Brigham (critical). Show today's live conditions (or a replayed snapshot), the recommendation, the map, the message, and "time saved vs. your usual way today".
3. **Download the .ics** and open it.
4. **Kiro:** show requirement 5.2 → design → task 6.6 → the property test, and one hook firing.

## Never commit
`.env`, `data/cache/`, real personal data.
