# Storm Twin: Longwood + Fenway

*Hackathon writeup — draft. This document opens with the problem, who it serves, and what the twin shows. The Kiro section is a placeholder to be finished in task 18.*

> **Honesty note:** every number this twin produces is a **simulation estimate** built from documented assumptions in `config/params.py`, not a calibrated or validated prediction. Read the map as "where to look first," not "exactly how long it will take."

## The problem

When a storm or a transit disruption hits the Longwood Medical Area and Fenway, most people adjust: they leave earlier, drive instead of taking the train, or wait it out. But the people with the **least slack** can't absorb the hit — elderly residents, people without a car, people with mobility needs who require step-free routes, and people on tight budgets who can't just book a ride.

Longwood is dense with the hospitals these residents depend on. The civic question Storm Twin answers is simple to ask and hard to see: *when the roads fill with snow and the Green Line E branch stops running, can these residents still reach the hospitals they count on — or does a snowstorm quietly cut a neighborhood off from care?*

## Who it serves

**Vulnerable residents** are the people the twin is built around:

- Residents aged 65+ living alone.
- Car-free households that rely on transit and walking.
- People with step-free mobility needs, for whom a broken elevator or an inaccessible shuttle stop means a route simply doesn't exist.
- People on tight transportation budgets, who can't fall back on a surge-priced ride.

**City planners** are the second audience. They need to see, at a glance, *where help is needed first* — which parts of Longwood and Fenway lose hospital access first and most severely as a storm builds, so plowing and outreach can be aimed at the right places.

## What the twin shows

Storm Twin is a **digital twin of the study-area road network** (Longwood + Fenway, drawn from OpenStreetMap). You describe a storm with a few sliders — snowfall, start time, the hour you're viewing, how many cars get moved off the street, and whether the Green Line E branch is suspended — and the twin recolors the map to match.

On the map you see:

- **Roads colored by capacity under the storm** — green where traffic still flows, shading toward red as snow and parked cars eat into capacity, black where a segment is closed or impassable. Snow emergency routes (Huntington Ave, Longwood Ave, Ruggles St, Tremont St, Hemenway St) get plowed more often and hold up better.
- **Origin dots colored by minutes to the nearest hospital** — for each intersection in the study area, the drive time to the closest of the three Longwood hospitals: **Beth Israel Deaconess, Brigham and Women's, and Boston Children's.**
- **KPIs on top** — the percent of origins "broken" (over 30 minutes to a hospital, or no route at all), the average minutes to a hospital across reachable origins, and the count of origins left unreachable.
- **A breaking-point map** — toggle the view and each area is colored by *how many inches of snow it takes to cut it off* from every hospital (and "never," in gray, for areas that hold). A sweep runs snowfall from 0 to 30 inches and records the first level at which each origin breaks.

Together these turn an abstract "big storm coming" into a concrete picture of which neighborhoods lose access, how fast, and at what snowfall.

*(Reminder: the colors and minutes are simulation assumptions, not measured values.)*

## How Kiro built this

Storm Twin was built spec-first in Kiro. Every feature below traces back to a written acceptance criterion, and the same criteria are what the tests, steering rules and review agent check against. The short version is in the ["How each Kiro feature is used"](./README.md) table in the README; this is the longer story.

### Spec — EARS requirements as the contract

The whole project starts from `.kiro/specs/longwood-storm-twin/`, written in the requirements → design → tasks order. The requirements use EARS notation ("WHEN … THE SYSTEM SHALL …"), so each promise is a single testable statement rather than a paragraph of intent. That mattered most for the promises that are easy to hand-wave: accessibility, budget, buffers for critical trips, and privacy are all spelled out as acceptance criteria with numbers attached (for example 5.2 for step-free routing, 6.1 for the 20-minute critical buffer, 11.3 for the 320-character message, 13.3 for never recommending an infeasible option). Every task in `tasks.md` cites the requirement numbers it satisfies, which is how four people could build in parallel against one `src/contract.py` without stepping on each other.

A concrete thread runs 5.2 → design → test: Requirement 5.2 says a step-free persona must never board at a stop with an active elevator outage; the design's testing-strategy section turns that into the property "a step-free persona is never routed through a non-step-free stop," and that becomes a Hypothesis test. The spec is the single source of truth the rest of the tooling points back to.

### Correctness — property-based tests

Alongside example-based unit tests, the core guarantees are checked with property-based tests (Hypothesis) so they hold across many inputs, not just the cases we thought of. The storm model's monotonicity (Requirement 3.6: more snow or lower parking compliance never makes any origin closer) is checked this way in the simulator tests; so is the message generator's hard contract (Requirement 11.3 / 13.3: for any label, time, duration and set of warnings, the composed message stays within 320 characters, always contains a clock time, and a broken trip always offers a safe fallback instead of the infeasible option). Property tests are annotated with the requirement they validate, so a failure points straight back to the spec.

### Steering — always, and fileMatch

Steering files in `.kiro/steering/` keep the team and the agent aligned without repeating context in every prompt:

- **Always-on** files load on every interaction: `product.md` (who we serve), `tech.md` (the stack), `structure.md` (the dependency direction — the simulator never imports adapters), and `privacy-and-messages.md` (the plain-language and privacy rules). The message generator in `src/outputs/messages.py` implements the message rules from that steering file line for line: 320-char cap, the "what changed → when to leave → how → time saved" order, always a clock time, rideshare costs only as "about $X–$Y," and no alarmist wording.
- **fileMatch** files load only when they are relevant: `simulation-assumptions.md` (model coefficients) loads when editing simulator code, and `data-sources.md` (API conventions) loads when editing adapters. This keeps the model's attention on the right numbers without crowding unrelated work.

### Hooks

Hooks in `.kiro/hooks/` automate the promises so they don't rely on anyone remembering:

- A **message checker** (`privacy-and-messages.json`) runs `pytest tests/outputs/test_messages.py` on every save of `src/outputs/messages.py` (and the templates), so a message that breaks the length or clock-time rule fails immediately.
- A **privacy guard** fires before file writes to re-assert the privacy rules — synthetic fixtures only, no medical reason stored, logs limited to ids/counts/timings.
- The simulator-tests and assumptions-sync hooks run the simulator tests on relevant edits and keep the documented assumptions in step with the code constants.

### MCP — the `boston-civic` server

`mcp_server/server.py`, wired up in `.kiro/settings/mcp.json`, is our own MCP server wrapping the MBTA and NWS APIs. It let us look at real alerts and forecasts from inside Kiro while writing the parsers, and the recorded responses in `tests/fixtures/` (MBTA alerts, NWS grid and alerts) came from it, so the adapter tests run offline. The accessibility-reviewer agent is also granted these tools so it can check whether a stop the planner relies on has a real elevator outage today.

### Custom agent — accessibility-reviewer

`.kiro/agents/accessibility-reviewer.json` is a read-plus-shell reviewer that advocates for the residents the twin serves. It loads the product, simulation-assumptions and privacy steering files plus the requirements doc, runs the blizzard demo over a set of synthetic personas, and audits every recommendation against Requirements 5, 6, 10, 12 and 13 — step-free routing, walking and budget limits, critical-trip buffers and reliability-first ranking, honest time-saved, and plain-language messages. It reads the three synthetic personas from `tests/fixtures/review_personas.json`. Its findings for this build are recorded in the next section.

### Skill — add-data-adapter

`.kiro/skills/add-data-adapter/` is a repeatable recipe for plugging in a new data source (becoming part of the base graph, a `Disruption`, or a persona attribute) without touching the simulator. It encodes the dependency rule from `structure.md` so a new adapter — MassDOT work zones is the obvious next one — follows the same shape as the MBTA and NWS adapters.

## Accessibility review findings

The accessibility-reviewer agent (`.kiro/agents/accessibility-reviewer.json`) is designed to run `python -m src.sim.demo --scenario blizzard --personas tests/fixtures/review_personas.json`. That demo module (`src/sim/demo`) is B-owned and is **not yet in the repo**, and a Kiro custom agent is invoked from the Kiro UI, not from within a task. So the live agent run is a **manual Kiro-UI step** and is flagged as a follow-up:

- **Follow-up for B:** add `src/sim/demo` with a `--scenario` and `--personas` CLI so the agent's command line works end to end.
- **Then (manual, Kiro UI):** open the accessibility-reviewer agent and run it; it will consume `tests/fixtures/review_personas.json` (already in place and valid: three synthetic personas) and report per-persona findings, including a live elevator-outage check via the `boston-civic` MCP tools.

In the meantime, a **manual accessibility pass** was done against Requirements 5, 6, 10, 12 and 13 on what this task owns — the message generator and the review personas:

- **Req 13.2 (synthetic data only):** `tests/fixtures/review_personas.json` contains three synthetic personas with generic study-area coordinates, no real names or addresses, and place labels only. Pass.
- **Req 13 / 4.3 (no medical reason):** trip labels are places ("Brigham pharmacy pickup," "Longwood clinic appointment," "Boston Children's front desk"), never a diagnosis or reason. The message generator only ever handles a label and times, and logs nothing. Pass.
- **Req 13.3 (never recommend an infeasible option):** `compose_message` routes any broken or unroutable trip to a fallback message ("reschedule, call ahead, or book The RIDE") and strips the normal mode summary, so it cannot tell someone to drive into a closed-road storm. Covered by a unit test and the property test. Pass.
- **Req 11.3 (message quality):** every message is ≤ 320 characters, in plain words, ordered what-changed → when-to-leave → how → time-saved, and always carries a clock time. Enforced by `check_message` and asserted inside `compose_message`; verified by 13 passing tests. Pass.
- **Req 10.3 (rideshare as a range):** `format_price_range` always renders "about $X–$Y," never a single quoted fare, even when the low and high are equal. Pass.
- **Reqs 5, 6, 12 (step-free routing, critical-trip buffers, sustainability ranking):** these live in the planner (`src/sim/*`), which this task does not own and which is not yet wired into a demo. The personas are shaped to exercise them — a 65+ step-free car-free resident with a **critical** Brigham pharmacy trip (should get the ≥ 20-minute buffer and reliability-first ranking, 6.1/6.4), a car-free budget-constrained rider ($8 budget, should push cost-aware ranking, 5.4/10), and a car-owning resident with an important appointment. **These three criteria cannot be confirmed here** and should be checked when the agent runs against the real demo. Deferred to the follow-up above.

Net: the message layer and the review fixtures pass their applicable accessibility and privacy checks; the planner-side criteria (5, 6, 12) are staged for the live agent run once `src/sim/demo` exists.
