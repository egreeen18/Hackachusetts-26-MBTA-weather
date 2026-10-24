---
inclusion: fileMatch
fileMatchPattern: ["src/sim/**/*.py", "src/contract.py", "config/**/*.py", "tests/**/test_sim*.py"]
---

# Simulation assumptions (v1, built today)

All numbers live in `config/params.py` and must match this file. They are **team assumptions, not calibrated values**; say so in the demo. Owner: D.

#[[file:config/params.py]]

## Model rules
1. **Snow accumulation:** total snowfall is spread evenly over `duration_hours` from `start_hour`. Each road tracks snow built up since its last plow pass.
2. **Plowing:** priority routes (Huntington Ave, Longwood Ave, Ruggles St, Tremont St, Hemenway St) every 2 h; other main roads every 4 h; side streets only `SIDE_STREET_PLOW_DELAY_H` after the snow stops.
3. **Parked cars** (priority routes only): capacity × `1 - PARKED_CAPACITY_LOSS × (1 - compliance)`; after each plow pass, `PARKED_PLOW_BLOCK × (1 - compliance)` of the snow stays.
4. **Capacity factor** from snow on the road: 0 in → 1.0, 2 → 0.7, 4 → 0.5, 8 → 0.3, linear between. Side streets with 12+ in are impassable.
5. **Travel time:** `t = free_flow_t / capacity_factor ** SPEED_EXPONENT × (1 + 0.15 × min(v/c, VC_CAP) ** 4)` (BPR), where `c` already includes snow and parked-car losses.
6. **Volume:** baseline v/c by road class and time of day, reduced by `DEMAND_DROP_PER_INCH` × snowfall (people stay home).
7. **Green Line E suspended:** v/c on Huntington Ave edges + `E_SUSPENSION_EXTRA_VC`.
8. **Broken** = more than 30 minutes to the nearest hospital, or unreachable.
9. **Breaking point:** sweep snowfall 0 → 30 in by 2 in (16 runs); each origin's breaking point is the first level at which it breaks.

## Guarantees (property tests check these)
- More snow never makes any edge faster or any origin closer.
- Higher parking compliance never makes things worse.
- 0 inches of snow gives capacity factor 1.0 everywhere.
- While snow is falling, priority routes never have more snow on them than side streets at the same hour.
