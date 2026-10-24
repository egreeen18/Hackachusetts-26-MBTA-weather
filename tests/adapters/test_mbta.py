"""Tests for the MBTA adapter (task 5.2). No live API calls: fixtures only.

Covers Requirements 8.1 (alerts -> flags) and 8.2 (elevator closures)."""
from __future__ import annotations

import json
from pathlib import Path

from src.adapters.mbta import parse_flags

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _load_alerts(name: str = "mbta_alerts.json") -> list[dict]:
    obj = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return obj["data"]


def test_green_e_suspension_sets_flag():
    flags = parse_flags(_load_alerts())
    assert flags["green_e_suspended"] is True


def test_elevator_closures_collected_without_filter():
    flags = parse_flags(_load_alerts())
    # Every ELEVATOR_CLOSURE stop, including the out-of-area one, when no filter.
    assert set(flags["elevators_out"]) == {"place-longw", "place-brmnl", "place-alfcl"}


def test_study_area_filter_excludes_outside_stops():
    study_area = {"place-longw", "place-brmnl"}
    flags = parse_flags(_load_alerts(), study_area_stops=study_area)
    assert set(flags["elevators_out"]) == {"place-longw", "place-brmnl"}
    assert "place-alfcl" not in flags["elevators_out"]


def test_green_d_delay_does_not_suspend_e():
    # A Green-D delay alert alone must not set green_e_suspended.
    alerts = [a for a in _load_alerts() if a["id"] == "alert-green-d-delay"]
    flags = parse_flags(alerts)
    assert flags["green_e_suspended"] is False
    assert flags["elevators_out"] == []


def test_empty_alerts_is_clear():
    flags = parse_flags([])
    assert flags == {"green_e_suspended": False, "elevators_out": []}


def test_flattened_mcp_shape_is_accepted():
    # The boston-civic MCP tool emits a flattened alert (no "attributes" wrapper).
    flattened = [{
        "id": "x",
        "effect": "SHUTTLE",
        "informed_entity": [{"route": "Green-E"}],
    }]
    flags = parse_flags(flattened)
    assert flags["green_e_suspended"] is True


def test_shuttle_effect_also_suspends_e():
    alerts = [{
        "attributes": {
            "effect": "SHUTTLE",
            "informed_entity": [{"route": "Green-E"}],
        }
    }]
    assert parse_flags(alerts)["green_e_suspended"] is True
