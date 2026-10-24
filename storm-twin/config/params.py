"""Every tunable number in the simulator lives here. Owner: D.
Mirrored in .kiro/steering/simulation-assumptions.md (a Kiro hook keeps them in sync).
These are ASSUMPTIONS for a hackathon model, not calibrated values. Say so in the demo.
"""

# Study area (Longwood Medical Area + Fenway)
BBOX = {"north": 42.350, "south": 42.330, "east": -71.085, "west": -71.115}

PRIORITY_ROUTES = ["Huntington Avenue", "Longwood Avenue", "Ruggles Street",
                   "Tremont Street", "Hemenway Street"]

# OSM highway tag -> road class
ROAD_CLASS = {
    "trunk": "main", "primary": "main", "secondary": "main", "tertiary": "main",
    "residential": "side", "unclassified": "side", "living_street": "side", "service": "side",
}  # anything tagged with a PRIORITY_ROUTES name becomes "priority" regardless of highway tag

# Plowing: hours between passes. None = only after the snow stops.
PLOW_INTERVAL_H = {"priority": 2, "main": 4, "side": None}
SIDE_STREET_PLOW_DELAY_H = 3        # side streets cleared this long after the storm ends

# Snow on the road (inches) -> capacity factor; linear between points
CAPACITY_TABLE = [(0, 1.0), (2, 0.7), (4, 0.5), (8, 0.3), (12, 0.2), (30, 0.1)]
SIDE_STREET_IMPASSABLE_IN = 12      # side streets with >= this much snow are closed

# Free-flow speed in snow: speed multiplier = capacity_factor ** SPEED_EXPONENT
SPEED_EXPONENT = 0.5

# Parked cars on priority routes (compliance = share moved)
PARKED_CAPACITY_LOSS = 0.5          # capacity *= 1 - PARKED_CAPACITY_LOSS * (1 - compliance)
PARKED_PLOW_BLOCK = 0.5             # after a plow pass, this share of snow stays where cars block it

# BPR congestion: t = t_snow * (1 + ALPHA * (v/c) ** BETA)
BPR_ALPHA = 0.15
BPR_BETA = 4
VC_CAP = 2.0                        # cap v/c so blizzard times stay plausible

# Baseline volume/capacity by road class and time of day (no real counts; assumption)
RUSH_HOURS = {7, 8, 9, 16, 17, 18}
NIGHT_HOURS = {0, 1, 2, 3, 4, 5, 22, 23}
BASE_VC = {
    "rush":  {"priority": 0.9, "main": 0.8, "side": 0.4},
    "day":   {"priority": 0.6, "main": 0.5, "side": 0.2},
    "night": {"priority": 0.2, "main": 0.2, "side": 0.1},
}
DEMAND_DROP_PER_INCH = 0.02         # people stay home: volume *= 1 - min(0.5, this * snow_inches)

# Green Line E branch suspended -> extra cars on Huntington Ave
E_SUSPENSION_EXTRA_VC = 0.25

# Outcomes
BROKEN_MINUTES = 30
SWEEP_MAX_IN = 30
SWEEP_STEP_IN = 2

# Sanity check D should run: a blizzard should make typical hospital trips
# 2-4x slower than a clear day, not 20x. Tune SPEED_EXPONENT / VC_CAP if not.
