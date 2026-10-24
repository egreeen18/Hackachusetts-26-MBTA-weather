"""Tests for the NWS adapter (task 9.2). No live API calls: fixture only.

Covers Requirement 8.3 (forecast -> storm-generator inputs)."""
from __future__ import annotations

import json
from pathlib import Path

from src.adapters.nws import (
    parse_storm_inputs,
    parse_active_alerts,
    _parse_duration_hours,
    _parse_valid_time,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _grid_props() -> dict:
    obj = json.loads((FIXTURES / "nws_grid.json").read_text(encoding="utf-8"))
    return obj["properties"]


def _alerts() -> dict:
    return json.loads((FIXTURES / "nws_alerts.json").read_text(encoding="utf-8"))


def test_total_snow_inches_from_mm():
    # 25.4 + 50.8 + 76.2 + 101.6 mm = 254 mm = 10.0 inches.
    out = parse_storm_inputs(_grid_props())
    assert out["snow_inches"] == 10.0


def test_start_hour_local_est():
    # First snow at 06:00 UTC; EST (UTC-5) -> 01:00 -> hour 1.
    out = parse_storm_inputs(_grid_props())
    assert out["start_hour"] == 1


def test_duration_spans_first_to_last():
    # 06:00 UTC start to 09:00+PT3H = 12:00 UTC end -> 6 hours.
    out = parse_storm_inputs(_grid_props())
    assert out["duration_hours"] == 6


def test_zero_snow_forecast():
    props = {"snowfallAmount": {"uom": "wmoUnit:mm", "values": [
        {"validTime": "2026-01-12T06:00:00+00:00/PT6H", "value": 0},
    ]}}
    out = parse_storm_inputs(props)
    assert out == {"snow_inches": 0.0, "start_hour": 0, "duration_hours": 0}


def test_missing_snow_series_is_safe():
    out = parse_storm_inputs({})
    assert out["snow_inches"] == 0.0


def test_duration_parsing():
    assert _parse_duration_hours("PT6H") == 6
    assert _parse_duration_hours("PT1H") == 1
    assert _parse_duration_hours("P1DT3H") == 27
    assert _parse_duration_hours("PT30M") == 0.5


def test_valid_time_split():
    start, hours = _parse_valid_time("2026-01-12T06:00:00+00:00/PT2H")
    assert start.hour == 6
    assert hours == 2


# ------------------------------------------------------------------ active alerts


def test_alerts_detect_winter_storm_product():
    # Fixture holds a Winter Storm Warning + a Wind Advisory.
    out = parse_active_alerts(_alerts())
    assert out["winter_storm_active"] is True
    assert "Winter Storm Warning" in out["events"]
    assert "Wind Advisory" in out["events"]


def test_alerts_wind_only_is_not_winter_storm():
    only_wind = {"features": [
        {"properties": {"event": "Wind Advisory"}},
    ]}
    out = parse_active_alerts(only_wind)
    assert out["winter_storm_active"] is False
    assert out["events"] == ["Wind Advisory"]


def test_alerts_empty_is_safe():
    out = parse_active_alerts({})
    assert out == {"winter_storm_active": False, "events": []}
