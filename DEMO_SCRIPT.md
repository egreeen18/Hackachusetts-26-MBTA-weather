# Storm Twin — 3-minute demo script

**Presenter:** D · **View:** City view (Streamlit app, `streamlit run app.py`) · **Target length:** ~3:00

> **Say this once, up front, and again at the close:** every number on screen is a
> **simulation estimate** from documented assumptions in `config/params.py` — not a
> calibrated or validated prediction (Requirement 7.4). Read the map as *"where to
> look first,"* not *"exactly how long it will take."*

Controls you touch, all in the left sidebar unless noted:
- **Preset scenario** dropdown — selects one of the three presets from `config/scenarios.py`.
- **Map view** radio (above the map) — `Hospital access` ↔ `Breaking point`.
- KPI cards on top of the City view: **Origins broken**, **Avg minutes to hospital**, **Unreachable origins**.

---

## 0:00–0:30 — Frame it (no clicks yet)

> "This is Storm Twin, a digital twin of the Longwood Medical Area and Fenway. The
> question it answers: when snow fills the roads and the Green Line E branch stops,
> can people still reach the three Longwood hospitals — Beth Israel Deaconess,
> Brigham and Women's, and Boston Children's — or does a storm quietly cut a
> neighborhood off from care? **One honesty note first: every number you'll see is a
> simulation estimate from our documented assumptions, not a measured value.**"

---

## 0:30–1:00 — Baseline: a clear day

**Do:** Set **Preset scenario** to **"Regular heavy snow"**, then drag the snowfall
slider to **0** (switch to *Custom* if needed) — or just start here to establish the
floor. Keep **Map view** on **Hospital access**.

**Say:**
> "Start with a calm baseline. Almost all of Longwood and Fenway reaches a hospital
> in a couple of minutes — our clear-day average is about **2 minutes**. The KPI cards
> up top are the headline: *Origins broken*, *Average minutes to hospital*, and
> *Unreachable origins*. Green roads, short trips. Again — these minutes are
> estimates, not calibrated numbers."

**Point at:** the three KPI cards; the mostly-green road network.

---

## 1:00–1:45 — Rush-hour blizzard

**Do:** Set **Preset scenario** to **"Rush-hour blizzard"** (18 in over 10 h from 6am,
viewed at hour 8 — the thick of the morning rush; low parking compliance).

**Say:**
> "Now a real storm, timed so the worst hours land on the morning rush. Watch the
> roads recolor toward red as snow and parked cars eat into capacity — the snow
> emergency routes like Huntington and Longwood Ave hold up better because they're
> plowed more often. Hospital trip times roughly **double to triple** versus a clear
> day: our headline is about a **2.6× median increase** in the rush-hour blizzard,
> against roughly **1.5×** for an ordinary heavy snow. The *Avg minutes to hospital*
> card jumps and more origins shift into the slow colors."

**Point at:** roads recoloring (green → red, black where closed); the KPI cards
climbing.

> *(Honesty beat)* "Still a simulation estimate — the ratio is what matters, not the
> exact minutes."

---

## 1:45–2:15 — Blizzard + E branch suspended

**Do:** Set **Preset scenario** to **"Blizzard + E branch suspended"** (same rush-hour
blizzard, same view hour 8, but the Green Line E is down).

**Say:**
> "Same blizzard, but now the Green Line E branch is suspended. Riders who'd normally
> take the train get pushed into cars, and that extra volume lands on **Huntington
> Ave**. The degradation nudges a little further — our median goes from about **2.6×
> to 2.7×** versus the clear day — concentrated along the corridor the E would have
> carried."

**Point at:** Huntington Ave recoloring; any additional KPI movement vs the previous
preset.

---

## 2:15–2:45 — Breaking-point map

**Do:** Keep the blizzard preset. Switch the **Map view** radio to **"Breaking point"**.
(It runs a snowfall sweep 0 → 30 in; give it a second.)

**Say:**
> "This is the planner's view. Instead of one storm, it sweeps snowfall from 0 to 30
> inches and colors each area by **how many inches it takes to cut it off** from every
> hospital. **Red is fragile** — it breaks at just a few inches. **Green is robust** —
> it holds until deep snow. **Gray is 'never'** — it doesn't break in our range. The
> red pockets are where access is lost first, so that's where plowing and outreach
> should be aimed first."

**Point at:** the red fragile areas (first to be cut off) vs the green/gray robust
ones.

---

## 2:45–3:00 — Close: who it serves

**Say:**
> "Storm Twin is built around the people with the least slack — residents 65+ living
> alone, car-free households, people who need step-free routes, people on tight
> budgets — and around **city planners** who need to see where help is needed first.
> And to be clear one more time: **every number here is a simulation estimate from
> our assumptions, not a validated prediction.** It tells you where to look first."

---

## Cheat sheet (headline numbers — all assumptions)

| Preset (exact label) | Snow / timing | Headline vs clear day |
|---|---|---|
| **Regular heavy snow** | 10 in / 8 h from 9am, view hr 13 | ~**1.5×** median trip time |
| **Rush-hour blizzard** | 18 in / 10 h from 6am, view hr 8 | ~**2.6×** median trip time |
| **Blizzard + E branch suspended** | same blizzard, E down, view hr 8 | ~**2.7×** median trip time |

Clear-day baseline ≈ 2 min average to a hospital. Source: headline numbers in
`.kiro/steering/simulation-assumptions.md` (task 8.2). **Numbers are team
assumptions, not calibrated values — say so (Requirement 7.4).**
