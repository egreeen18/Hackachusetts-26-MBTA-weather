---
inclusion: fileMatch
fileMatchPattern: ["src/sim/**/*.py", "src/contract.py", "config/**/*.py", "tests/**/test_sim*.py"]
---

# Simulation assumptions (v1, built today)

All numbers live in `config/params.py` and must match this file. They are **team assumptions, not calibrated values**; say so in the demo. Owner: D.

#[[file:config/params.py]]

## Model rules
1. **Snow accumulation:** total snowfall is spread evenly over `duration_hours` from `start_hour`. Each road tracks snow built up since its last plow pass.
2. **Plowing** (`PLOW_INTERVAL_H`): priority routes (`PRIORITY_ROUTES`: Huntington Ave, Longwood Ave, Ruggles St, Tremont St, Hemenway St) every 2 h; other main roads every 4 h; side streets only `SIDE_STREET_PLOW_DELAY_H` (3 h) after the snow stops. Road class comes from the OSM highway tag via `ROAD_CLASS`; any edge named in `PRIORITY_ROUTES` is "priority" regardless of tag.
3. **Parked cars** (priority routes only): capacity × `1 - PARKED_CAPACITY_LOSS × (1 - compliance)` (`PARKED_CAPACITY_LOSS` = 0.5); after each plow pass, `PARKED_PLOW_BLOCK × (1 - compliance)` of the snow stays (`PARKED_PLOW_BLOCK` = 0.5). `compliance` is the share of cars moved (`parking_compliance`, 0–1).
4. **Capacity factor** from snow on the road (`CAPACITY_TABLE`): 0 in → 1.0, 2 → 0.7, 4 → 0.5, 8 → 0.3, 12 → 0.2, 30 → 0.1, linear between the points. Side streets with `SIDE_STREET_IMPASSABLE_IN` (12) or more inches are impassable.
5. **Travel time:** `t = free_flow_t / capacity_factor ** SPEED_EXPONENT × (1 + BPR_ALPHA × min(v/c, VC_CAP) ** BPR_BETA)` (BPR), with `SPEED_EXPONENT` = 1.75, `BPR_ALPHA` = 0.15, `BPR_BETA` = 4, `VC_CAP` = 2.0; `c` already includes snow and parked-car losses.
6. **Volume:** baseline v/c by road class and time of day from `BASE_VC` — rush {priority 0.9, main 0.8, side 0.4}, day {0.6, 0.5, 0.2}, night {0.2, 0.2, 0.1} — reduced by `volume × (1 - min(0.5, DEMAND_DROP_PER_INCH × snow_inches))` (people stay home; `DEMAND_DROP_PER_INCH` = 0.02, capped at 0.5). `RUSH_HOURS` = {7,8,9,16,17,18}, `NIGHT_HOURS` = {0-5,22,23}; all other hours are "day".
7. **Green Line E suspended:** v/c on Huntington Ave edges + `E_SUSPENSION_EXTRA_VC` (0.25).
8. **Broken** = more than `BROKEN_MINUTES` (30) minutes to the nearest hospital, or unreachable.
9. **Breaking point:** sweep snowfall 0 → `SWEEP_MAX_IN` (30) in by `SWEEP_STEP_IN` (2) in (16 runs); each origin's breaking point is the first level at which it breaks.

## Constants reference (mirror of `config/params.py`)
Every tunable in `config/params.py` with its value and why. If a number changes in one place, change it in both.

| Constant | Value | Rationale |
|---|---|---|
| `BBOX` | N 42.350, S 42.330, E -71.085, W -71.115 | Longwood Medical Area + Fenway; matches the requirements study area. |
| `PRIORITY_ROUTES` | Huntington Ave, Longwood Ave, Ruggles St, Tremont St, Hemenway St | Boston snow emergency routes in the study area. |
| `ROAD_CLASS` | trunk/primary/secondary/tertiary → main; residential/unclassified/living_street/service → side | OSM highway tag → class; a `PRIORITY_ROUTES` name overrides to "priority". |
| `PLOW_INTERVAL_H` | priority 2, main 4, side None | Req 3.2: priority every 2 h, main every 4 h, side only after snow stops. |
| `SIDE_STREET_PLOW_DELAY_H` | 3 | Side streets cleared 3 h after the storm ends (assumption). |
| `CAPACITY_TABLE` | (0,1.0),(2,0.7),(4,0.5),(8,0.3),(12,0.2),(30,0.1) | Snow-on-road → capacity factor, linear between; monotonically decreasing. |
| `SIDE_STREET_IMPASSABLE_IN` | 12 | Req 3.4: side streets with ≥12 in are closed. |
| `SPEED_EXPONENT` | 1.75 | Free-flow speed multiplier = capacity_factor ** 1.75. Tuned in task 8.2 so a blizzard is a median ~2.6x slower than a clear day (2-4x sanity target); 0.5 gave only ~1.3x. Raising it cannot fragment the network (only capacity_factor == 0 closes an edge). |
| `PARKED_CAPACITY_LOSS` | 0.5 | Capacity loss per unit of non-compliance on priority routes. |
| `PARKED_PLOW_BLOCK` | 0.5 | Share of snow left behind parked cars after a plow pass. |
| `BPR_ALPHA` | 0.15 | Standard BPR coefficient. |
| `BPR_BETA` | 4 | Standard BPR exponent. |
| `VC_CAP` | 2.0 | Caps v/c so blizzard travel times stay plausible. |
| `RUSH_HOURS` | {7,8,9,16,17,18} | Morning and evening peaks. |
| `NIGHT_HOURS` | {0,1,2,3,4,5,22,23} | Overnight low demand; all other hours are "day". |
| `BASE_VC` | rush {0.9,0.8,0.4}, day {0.6,0.5,0.2}, night {0.2,0.2,0.1} (priority, main, side) | Assumed baseline v/c; no real counts. Monotonic in demand and class. |
| `DEMAND_DROP_PER_INCH` | 0.02 | People stay home: volume × (1 − min(0.5, 0.02 × snow_inches)). |
| `E_SUSPENSION_EXTRA_VC` | 0.25 | Req 3.5: extra car volume on Huntington Ave when the E branch is suspended. |
| `BROKEN_MINUTES` | 30 | Req 15.2: origin is broken above 30 min to nearest hospital. |
| `SWEEP_MAX_IN` | 30 | Req 15.4: breaking-point sweep upper bound. |
| `SWEEP_STEP_IN` | 2 | Req 15.4: 2-inch steps (0→30 = 16 runs). |

## Guarantees (property tests check these)
- More snow never makes any edge faster or any origin closer.
- Higher parking compliance never makes things worse.
- 0 inches of snow gives capacity factor 1.0 everywhere.
- While snow is falling, priority routes never have more snow on them than side streets at the same hour.

## Headline numbers (task 8.2)

Sanity check for Requirement 3.8: a blizzard should make typical hospital trips
2–4× slower than a clear day, not 20× and not negligible. Run on the cached
drive graph (649 nodes, 1444 edges, ~594 origins reachable on a clear day; 12
origins are topology-disconnected and unreachable even on a clear day — a graph
issue for A, not a weather effect). Clear-day baseline is taken at the **same
clock hour** as each scenario so time-of-day congestion is matched; the
representative ratio is the **median per-origin** storm/clear ratio over the
~594 origins reachable in both runs (the mean over avg-minutes is diluted by
the many origins very close to a hospital).

With `SPEED_EXPONENT` = 1.75 (tuned up from 0.5), `VC_CAP` = 2.0 (unchanged):

| Scenario (view hour) | clear avg | storm avg | median per-trip ratio | p90 ratio |
|---|---|---|---|---|
| Regular heavy snow (13) | 2.0 min | 3.1 min | **1.5×** | 2.1× |
| Rush-hour blizzard (8) | 2.1 min | 5.4 min | **2.6×** | 2.9× |
| Blizzard + E suspended (8) | 2.1 min | 5.5 min | **2.7×** | 2.9× |

`pct_broken` stays ~2.0% and `n_unreachable` stays 12 in every run — tuning the
speed exponent slows roads but never closes them, so the network does not
fragment. **Demo line:** "A blizzard roughly doubles-to-triples the drive time
to the nearest hospital across Longwood; an ordinary heavy snow adds about half
again." Say the numbers are assumptions, not calibrated values.

Why `SPEED_EXPONENT` and not `VC_CAP`: the storm/clear ratio is driven almost
entirely by the snow→capacity channel `(1/cap)**SPEED_EXPONENT`. The BPR v/c
term is (by design, for the monotonicity invariant) the same clear vs storm
except for the small E-suspension bump on Huntington Ave, so `VC_CAP` barely
moves the ratio and was left at 2.0.

Post-hackathon (B/D): the absolute trip times are small (~2–6 min) for a ~2 km
study area, so `BROKEN_MINUTES` = 30 is never reached by weather alone — "broken"
today is effectively "unreachable". To make the broken threshold bite from
weather, calibrate free-flow times against real door-to-door data (include
in-vehicle + access time, not just edge traversal), and consider a snow-aware
demand drop that preserves monotonicity so congestion also contributes.
