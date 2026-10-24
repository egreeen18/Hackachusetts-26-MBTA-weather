"""Demo scenarios for the Longwood Storm Twin (Requirement 3.8).

Ships the three named demo scenarios the UI preset dropdown (task 11.1) and the
demo script (task 12) select between:

  1. regular heavy snow
  2. rush-hour blizzard
  3. blizzard with the Green Line E branch suspended

Each scenario dict is exactly contract-shaped: its keys are the keys of the
``Scenario`` TypedDict in ``src/contract.py`` (snow_inches, start_hour,
duration_hours, parking_compliance, green_e_suspended, elevators_out). The
view-hour, label and blurb live *alongside* each scenario in the ``SCENARIOS``
registry, never inside the scenario dict, so the dict stays safe to pass
straight into ``run_simulation(scenario, hour)``.

Numbers are team assumptions, not calibrated values; they are chosen to be
self-consistent with ``.kiro/steering/simulation-assumptions.md`` (RUSH_HOURS =
{7,8,9,16,17,18}; snow spread evenly over duration_hours from start_hour). D
tunes these further in task 8.2.

Import from here:

    from config.scenarios import SCENARIOS           # ordered registry
    preset = SCENARIOS["rush_hour_blizzard"]
    result = run_simulation(preset["scenario"], preset["view_hour"])
"""
from __future__ import annotations

from typing import TypedDict

from src.contract import Scenario


# ---------------------------------------------------------------- the scenarios

# A solid, ordinary heavy snowstorm. Starts mid-morning (after the rush) and
# lasts the working day. Decent parking compliance. E branch running normally.
REGULAR_HEAVY_SNOW: Scenario = {
    "snow_inches": 10,
    "start_hour": 9,
    "duration_hours": 8,
    "parking_compliance": 0.7,
    "green_e_suspended": False,
    "elevators_out": [],
}

# A bigger storm timed so the heaviest hours land on the morning rush. Starts at
# 6 so snow is already building when the 7-9 peak hits; lower parking compliance
# (people don't move their cars in a blizzard). E branch still running.
RUSH_HOUR_BLIZZARD: Scenario = {
    "snow_inches": 18,
    "start_hour": 6,
    "duration_hours": 10,
    "parking_compliance": 0.4,
    "green_e_suspended": False,
    "elevators_out": [],
}

# The same rush-hour blizzard, but with the Green Line E branch suspended, which
# pushes extra car volume onto Huntington Ave (E_SUSPENSION_EXTRA_VC).
BLIZZARD_E_SUSPENDED: Scenario = {
    "snow_inches": 18,
    "start_hour": 6,
    "duration_hours": 10,
    "parking_compliance": 0.4,
    "green_e_suspended": True,
    "elevators_out": [],
}


# ---------------------------------------------------------------- the registry

class Preset(TypedDict):
    """One entry in the demo preset registry.

    ``scenario`` is passed to ``run_simulation`` / ``sweep_snow`` unchanged;
    ``view_hour`` is the hour the UI should display this scenario at by default.
    """
    label: str          # dropdown label
    blurb: str          # one-line description for the UI / demo narration
    scenario: Scenario  # contract-shaped scenario dict
    view_hour: int      # default hour to display (0-23)


# Ordered mapping name -> Preset. Insertion order is the dropdown order, so the
# UI can iterate ``SCENARIOS.items()`` directly. Python dicts preserve order.
SCENARIOS: dict[str, Preset] = {
    "regular_heavy_snow": {
        "label": "Regular heavy snow",
        "blurb": "10 in over 8 h from mid-morning; most cars moved off priority routes.",
        "scenario": REGULAR_HEAVY_SNOW,
        # Mid-storm: starts 9, lasts 8 h (ends 17), so 13 is the thick of it.
        "view_hour": 13,
    },
    "rush_hour_blizzard": {
        "label": "Rush-hour blizzard",
        "blurb": "18 in over 10 h starting 6am; peak lands on the 7-9 rush, few cars moved.",
        "scenario": RUSH_HOUR_BLIZZARD,
        # Inside the morning rush with snow already piling up.
        "view_hour": 8,
    },
    "blizzard_e_suspended": {
        "label": "Blizzard + E branch suspended",
        "blurb": "Rush-hour blizzard with the Green Line E down, pushing cars onto Huntington Ave.",
        "scenario": BLIZZARD_E_SUSPENDED,
        # Same peak-rush viewing hour so the E-suspension effect is visible.
        "view_hour": 8,
    },
}

# Convenience list of (name, Preset) in dropdown order, for callers that prefer
# a sequence over a mapping.
PRESETS: list[tuple[str, Preset]] = list(SCENARIOS.items())


# ---------------------------------------------------------------- self-check

# The exact set of keys the Scenario contract defines. Kept here so the
# self-check below fails loudly if a scenario drifts out of contract shape.
_CONTRACT_KEYS = {
    "snow_inches",
    "start_hour",
    "duration_hours",
    "parking_compliance",
    "green_e_suspended",
    "elevators_out",
}


def _self_check() -> None:
    assert set(Scenario.__annotations__) == _CONTRACT_KEYS, (
        "Scenario contract keys changed; update config/scenarios.py to match "
        "src/contract.py"
    )
    for name, preset in SCENARIOS.items():
        scenario = preset["scenario"]
        assert set(scenario) == _CONTRACT_KEYS, (
            f"preset {name!r} scenario keys {sorted(scenario)} != contract keys "
            f"{sorted(_CONTRACT_KEYS)}"
        )
        assert 0 <= preset["view_hour"] <= 23, f"preset {name!r} view_hour out of range"
        assert 0 <= scenario["start_hour"] <= 23, f"preset {name!r} start_hour out of range"
        assert 0.0 <= scenario["parking_compliance"] <= 1.0, (
            f"preset {name!r} parking_compliance out of range"
        )
    print(f"config.scenarios OK: {len(SCENARIOS)} presets, all contract-shaped.")


if __name__ == "__main__":
    _self_check()
