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

<!-- PLACEHOLDER — to be completed in task 18 (D). -->

*This section will describe how each Kiro feature was used to build Storm Twin. The source of truth is the **"How each Kiro feature is used"** table in [`README.md`](./README.md) — covering the Spec (14 EARS requirements), Correctness property-based tests, always-on and fileMatch Steering, Hooks, the `boston-civic` MCP server, the accessibility-reviewer custom agent, and the add-data-adapter skill. Expand that table into prose here, with concrete examples (e.g. requirement 5.2 → design → property test, and a hook firing on a simulator edit).*
