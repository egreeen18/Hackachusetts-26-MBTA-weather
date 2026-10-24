# Requirements Document

## Introduction

**Storm Twin** is a digital twin of the Longwood Medical Area and Fenway (Boston) plus a personal travel agent built on top of it.

The twin answers one civic question: *when a storm or transit disruption hits, can the people with the least slack (elderly residents, people without a car, people with mobility needs, people on tight budgets) still reach the hospitals and pharmacies they depend on?*

The agent uses the same twin for one person at a time. It reads their schedule, watches live MBTA and National Weather Service data, simulates their trips under current conditions, and recommends what to do (leave earlier, switch mode, avoid a broken elevator, book a ride within budget) before they leave the house.

Build order: **the simulator comes first.** Live data and the agent are adapters on top of it. Every live, historical or synthetic event becomes the same `Disruption` object, so the simulator never needs to know where an event came from.

### Scope for today (deadline 6pm)

- **Built today, simulator (must have):** Requirements 1.1, 1.3, 1.4, 3, 7.4, 15, 16.
- **Built today if the simulator is done by 3:45 (nice to have):** live MBTA and weather inputs (8.1, 8.2, 8.3, 8.4), one persona's trip check (4.1, 4.3, 16.3), a calendar file and short message (11.1, 11.3), privacy rules (13).
- **After the hackathon:** full transit planner and rideshare options (5, 6, 10, 12), seasonal patterns (9), Census synthetic personas (4.4, 7.3), validation layers (14).

### Study area

Bounding box (approximate, tune as needed): north 42.350, south 42.330, east -71.085, west -71.115. It covers Beth Israel Deaconess, Brigham and Women's and Boston Children's; the Green Line D branch (Fenway, Longwood) and E branch (Northeastern through Brigham Circle); the bus routes serving Longwood; and the snow emergency routes Huntington Ave, Longwood Ave, Ruggles St, Tremont St and Hemenway St.

## Glossary

- **Twin**: the road, walking and transit networks of the study area, held as graphs.
- **Disruption**: one change to the twin (a slowed or closed road segment, a suspended transit segment, a shuttle replacement, an elevator outage, a rideshare surge). Has a source, severity and active period.
- **Scenario**: a named set of Disruptions applied together, for example "8 inches of snow, Tuesday 8am" or "live conditions right now".
- **Persona**: a user profile, either real (from onboarding) or synthetic (generated from Census shares for the demo).
- **Trip**: one scheduled journey of a persona: origin, destination, arrival deadline, priority, usual mode.
- **Critical trip**: a trip with priority `critical` (hospital, dialysis, medication pickup).
- **Option**: one way to make a trip (walk, transit, rideshare or a combination) with travel time, cost, carbon estimate and feasibility.
- **Stranded**: no feasible option meets the persona's constraints and deadline.

## Requirements

### Requirement 1: Base network of the study area

**User Story:** As a developer, I want the real road, walking and transit networks of Longwood and Fenway loaded as graphs, so that every simulation runs on real geography.

#### Acceptance Criteria

1. WHEN the twin initializes THE SYSTEM SHALL load the drivable and walkable street networks for the study-area bounding box from OpenStreetMap and store them as graphs with edge length and free-flow travel time.
2. WHEN the twin initializes THE SYSTEM SHALL build a transit graph from MBTA static GTFS containing every stop, route and scheduled headway inside the bounding box, including Green Line D and E branch stops and the bus routes serving the area.
3. WHEN a network has been fetched once THE SYSTEM SHALL cache it locally and load it from the cache on later runs, so the demo works without network access.
4. THE SYSTEM SHALL tag each street edge that belongs to a snow emergency route.
5. THE SYSTEM SHALL tag each transit stop with its wheelchair accessibility and the elevators that serve it, using MBTA stop and facilities data.
6. THE SYSTEM SHALL tag Green Line E branch segments that run in the street on Huntington Avenue as street-running.

### Requirement 2: One disruption model for every source

**User Story:** As a developer, I want live, historical and synthetic events to share one data model, so that the simulator is tested once and reused everywhere.

#### Acceptance Criteria

1. THE SYSTEM SHALL represent every change to the twin as a Disruption with kind, target, severity, active period, source and a human-readable reason.
2. THE SYSTEM SHALL support at least these kinds: road_slowdown, road_closure, transit_delay, transit_suspension, shuttle_replacement, elevator_outage, rideshare_surge.
3. WHEN the simulator applies a Scenario THE SYSTEM SHALL depend only on Disruption objects and never on the source that produced them.
4. WHEN two Disruptions target the same element at the same time THE SYSTEM SHALL apply the most severe one.
5. WHEN a Scenario is applied and then removed THE SYSTEM SHALL return the twin to exactly its baseline state.

### Requirement 3: Blizzard road model (snow, plowing, parked cars, congestion)

**User Story:** As a team, we want to describe a storm with a few numbers and see how every road in Longwood and Fenway degrades hour by hour, so that we can simulate blizzards that are not happening right now.

#### Acceptance Criteria

1. WHEN given a scenario (snow_inches, start_hour, duration_hours, parking_compliance, green_e_suspended) and an hour THE SYSTEM SHALL compute, for every road segment, snow on the road since its last plow pass, a capacity factor and a travel time, using only the rules and values in `config/params.py`.
2. THE SYSTEM SHALL spread total snowfall evenly over the storm hours and plow priority routes every 2 hours, other main roads every 4 hours, and side streets only after the snow stops.
3. WHEN parking compliance is below 1 THE SYSTEM SHALL reduce priority-route capacity and plowing effectiveness in proportion to the cars left.
4. THE SYSTEM SHALL compute congested travel time with the BPR formula, and SHALL close side streets with 12 or more inches of snow.
5. WHEN the Green Line E branch is suspended THE SYSTEM SHALL increase car volume on Huntington Avenue.
6. WHEN snowfall increases or parking compliance decreases with everything else unchanged THE SYSTEM SHALL NOT decrease the travel time of any segment.
7. WHEN snowfall is zero THE SYSTEM SHALL give every segment a capacity factor of 1.0.
8. THE SYSTEM SHALL ship three demo scenarios: regular heavy snow, rush-hour blizzard, and blizzard with the E branch suspended.

### Requirement 4: Personas and onboarding profile

**User Story:** As a resident, I want to tell the system my schedule, how I get around, my limits and my budget once, so that recommendations fit my real life.

#### Acceptance Criteria

1. THE SYSTEM SHALL store for each persona: home location, age group, mobility needs (step-free required, maximum walking distance), car access, rideshare budget per trip, sustainability preference and a list of Trips.
2. THE SYSTEM SHALL store for each Trip: destination label and location, arrival deadline, recurrence, usual mode and priority (critical, important or flexible).
3. WHEN onboarding a destination THE SYSTEM SHALL store a place label and location only, and SHALL NOT ask for or store a medical reason.
4. WHEN running the city-scale demo THE SYSTEM SHALL generate synthetic personas whose shares of residents aged 65+ living alone and of households without a car match Census ACS data for each tract.

### Requirement 5: Multimodal planning under disruption

**User Story:** As a resident, I want the system to find a way to my appointment that I can actually take during the disruption, so that I do not get stuck.

#### Acceptance Criteria

1. WHEN planning a Trip under a Scenario THE SYSTEM SHALL evaluate walk, transit, rideshare and combined options and return them ranked.
2. IF a persona requires step-free access THEN THE SYSTEM SHALL exclude any option that boards or alights at a stop that is not accessible or that has an active elevator outage.
3. IF an option's walking distance exceeds the persona's maximum THEN THE SYSTEM SHALL mark it infeasible.
4. IF an option's estimated cost exceeds the persona's budget THEN THE SYSTEM SHALL mark it over budget and rank it below every feasible in-budget option.
5. IF no option is feasible before the deadline THEN THE SYSTEM SHALL mark the Trip stranded and suggest fallback resources: The RIDE paratransit, rescheduling, calling the destination, or a trusted contact.
6. WHEN an option uses a shuttle replacement THE SYSTEM SHALL add boarding delay and check the shuttle stop against the persona's accessibility needs.

### Requirement 6: Priority and buffers

**User Story:** As a person with a critical appointment, I want more safety margin than for a routine trip, so that I arrive even if things get worse.

#### Acceptance Criteria

1. WHEN planning a critical Trip THE SYSTEM SHALL add a buffer of at least 20 minutes to the recommended departure time.
2. WHEN planning an important Trip THE SYSTEM SHALL add a buffer of at least 10 minutes.
3. WHEN a critical Trip is affected by any Disruption THE SYSTEM SHALL notify the persona regardless of the size of the delay.
4. WHEN ranking options for a critical Trip THE SYSTEM SHALL prefer reliability (fewer transfers, fewer disrupted segments) over speed.

### Requirement 7: Impact metrics and time saved

**User Story:** As a judge or city planner, I want honest numbers on what the disruption costs and what the recommendation saves, so that the impact is measurable.

#### Acceptance Criteria

1. WHEN a Scenario is run for a Trip THE SYSTEM SHALL compute the baseline outcome (usual mode and usual departure, under the Scenario) and the recommended outcome (under the same Scenario).
2. THE SYSTEM SHALL report time saved as baseline arrival delay minus recommended arrival delay, and SHALL NOT report time saved against a no-disruption baseline.
3. WHEN a Scenario is run city-wide THE SYSTEM SHALL report, per Census tract, the share of synthetic personas who can reach a Longwood hospital within 30 minutes, and the count stranded.
4. WHEN reporting any metric THE SYSTEM SHALL label it as a simulation estimate.

### Requirement 8: Live data adapters

**User Story:** As a resident, I want recommendations based on what is happening now, so that I am warned about real disruptions.

#### Acceptance Criteria

1. WHEN polling MBTA alerts THE SYSTEM SHALL convert each active alert affecting the study area into Disruptions, using the alert's informed entities, effect and active period.
2. WHEN polling MBTA alerts and facilities THE SYSTEM SHALL convert each elevator outage at a study-area stop into an elevator_outage Disruption.
3. WHEN polling the National Weather Service THE SYSTEM SHALL fetch active alerts and gridded forecast values for the study area and convert winter-storm and high-wind products into storm-generator inputs.
4. IF a live source fails or times out THEN THE SYSTEM SHALL use the last successful snapshot and label results as based on stale data with its timestamp.
5. THE SYSTEM SHALL record every live snapshot to disk with a timestamp, so it can be replayed as a Scenario later.

### Requirement 9: Seasonal and historical patterns

**User Story:** As a rider, I want a heads-up when a line is often disrupted at this time of year, so that I plan with realistic expectations.

#### Acceptance Criteria

1. WHEN historical reliability data is available for a line THE SYSTEM SHALL compute a disruption base rate by line, month and day of week.
2. WHEN a Trip uses a line whose base rate exceeds a configurable threshold THE SYSTEM SHALL include a heads-up stating the rate as a historical frequency, not a prediction.
3. IF no historical data is available for a line THEN THE SYSTEM SHALL omit the heads-up rather than guess.

### Requirement 10: Rideshare cost estimate

**User Story:** As a resident on a budget, I want an honest estimate of what a ride would cost right now, so that I can decide whether I can afford it.

#### Acceptance Criteria

1. THE SYSTEM SHALL estimate rideshare cost as base fare plus per-mile and per-minute charges, multiplied by a surge factor, using coefficients documented in the `simulation-assumptions` steering file.
2. WHEN a Scenario includes a storm or a rail suspension in the study area THE SYSTEM SHALL raise the surge factor according to the documented assumptions.
3. THE SYSTEM SHALL display every rideshare cost as an estimated range and SHALL NOT present it as a quote.
4. THE SYSTEM SHALL NOT call any rideshare company API; booking is handed off to the rider's own app.

### Requirement 11: Outputs

**User Story:** As a resident, I want the recommendation in my calendar, on a map and as a short message, so that I can act on it without opening another app.

#### Acceptance Criteria

1. WHEN a recommendation changes a Trip THE SYSTEM SHALL export an .ics file containing a "Leave by" event and the travel block for that Trip.
2. WHEN showing a recommendation THE SYSTEM SHALL draw the recommended and baseline routes on a map, with disrupted segments highlighted.
3. WHEN notifying a persona THE SYSTEM SHALL produce a plain-language message of at most 320 characters stating what changed, when to leave and how, and the time saved.
4. WHEN running the city-scale demo THE SYSTEM SHALL show a map of tract-level hospital reachability under the selected Scenario.

### Requirement 12: Sustainability preference

**User Story:** As a resident who cares about the environment, I want lower-carbon options preferred when they cost me little time, so that my choices match my values.

#### Acceptance Criteria

1. THE SYSTEM SHALL estimate grams of CO2 for every option using per-mode emission factors documented in the `simulation-assumptions` steering file.
2. WHEN a persona has a sustainability preference AND a lower-carbon feasible option arrives within 10 minutes of the fastest feasible option THE SYSTEM SHALL rank the lower-carbon option first, except for critical Trips.

### Requirement 13: Privacy and safety

**User Story:** As a resident, I want my schedule handled carefully, so that using the service does not expose me.

#### Acceptance Criteria

1. THE SYSTEM SHALL NOT write persona names, home addresses or trip destinations to logs.
2. THE SYSTEM SHALL use only synthetic personas in demos and committed fixtures.
3. WHEN generating any message THE SYSTEM SHALL NOT recommend an option marked infeasible for that persona.

### Requirement 15: Hospital access and breaking points

**User Story:** As a city planner, I want to see how long each part of Longwood and Fenway takes to reach a hospital in a storm, and how much snow it takes to cut each area off, so that I know where help is needed first.

#### Acceptance Criteria

1. WHEN a simulation runs THE SYSTEM SHALL compute, for every origin, the minutes to the nearest of Beth Israel Deaconess, Brigham and Women's and Boston Children's.
2. THE SYSTEM SHALL mark an origin broken WHEN its time to the nearest hospital exceeds 30 minutes OR no route exists.
3. THE SYSTEM SHALL report KPIs: percent of origins broken, average minutes to a hospital over reachable origins, and the number unreachable.
4. WHEN a breaking-point sweep runs THE SYSTEM SHALL simulate snowfall from 0 to 30 inches in 2-inch steps and record, for each origin, the first snowfall at which it breaks, or none.

### Requirement 16: Simulator interface contract

**User Story:** As a teammate building the UI or the personal agent, I want a small fixed set of functions to call, so that I can work in parallel with the simulator.

#### Acceptance Criteria

1. THE SYSTEM SHALL expose the simulator only through `run_simulation(scenario, hour)`, `sweep_snow(scenario)` and `trip_time(origin, dest, scenario, hour)` as defined in `src/contract.py`.
2. THE SYSTEM SHALL keep the return shapes in `src/contract.py` stable; any change is agreed by the whole team first.
3. WHEN `trip_time` is called THE SYSTEM SHALL return storm travel time, clear-day travel time, whether the trip is broken, how much earlier to leave, the route, and warnings such as an elevator outage at a stop in `elevators_out`.

### Requirement 14: Validation (stretch)

**User Story:** As a judge, I want evidence that the storm model resembles reality, so that I trust the simulation.

#### Acceptance Criteria

1. WHEN 311 snow and plowing requests for a past storm date are loaded THE SYSTEM SHALL compare their street-level clusters with the streets the storm generator slows most, and report the overlap.
2. WHEN Vision Zero crash records are loaded THE SYSTEM SHALL display crash hotspots as an optional risk layer, noting that the data comes from city dispatch records and does not fully match the state crash database.
3. WHEN NOAA buoy 44013 observations are loaded THE SYSTEM SHALL show falling pressure and rising wind as an "approaching storm" indicator, labeled as an offshore observation.
