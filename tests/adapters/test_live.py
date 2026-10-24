"""Tests for the live-scenario aggregator (task 15). No live network calls:
``nws_storm_inputs`` and ``mbta_flags`` are monkeypatched.

Covers Requirement 8.4 (stale data is labelled with its timestamp) and confirms
the fresh path reports fresh. Snapshot writing (Requirement 8.5) lives inside the
adapters and is exercised by their own tests; here we only confirm the aggregator
does not interfere and reports freshness correctly.
"""
from __future__ import annotations

from datetime import datetime, timezone

import src.adapters.live as live
from src.adapters.live import DEFAULT_PARKING_COMPLIANCE, live_scenario


def _patch(monkeypatch, nws_inputs, nws_fetched, mbta_flags_val, mbta_fetched):
    monkeypatch.setattr(live, "nws_storm_inputs",
                        lambda *a, **k: (nws_inputs, nws_fetched))
    monkeypatch.setattr(live, "mbta_flags",
                        lambda *a, **k: (mbta_flags_val, mbta_fetched))


# ------------------------------------------------------------------ fresh path


def test_fresh_merges_both_sources_into_scenario(monkeypatch):
    ts = "2026-01-12T14:30:00+00:00"
    _patch(
        monkeypatch,
        nws_inputs={"snow_inches": 8.0, "start_hour": 7, "duration_hours": 10,
                    "stale_since": None},
        nws_fetched=ts,
        mbta_flags_val={"green_e_suspended": True,
                        "elevators_out": ["place-longw", "place-brmnl"],
                        "stale_since": None},
        mbta_fetched=ts,
    )
    scenario, meta = live_scenario()

    # NWS fields.
    assert scenario["snow_inches"] == 8.0
    assert scenario["start_hour"] == 7
    assert scenario["duration_hours"] == 10
    # MBTA fields.
    assert scenario["green_e_suspended"] is True
    assert scenario["elevators_out"] == ["place-longw", "place-brmnl"]
    # Not a live signal -> sensible default.
    assert scenario["parking_compliance"] == DEFAULT_PARKING_COMPLIANCE

    # Freshness: both fresh, nothing stale, not the no-data fallback.
    assert meta["nws"]["fresh"] is True
    assert meta["mbta"]["fresh"] is True
    assert meta["any_stale"] is False
    assert meta["no_live_data"] is False
    # A usable "data as of" is always present.
    assert meta["data_as_of_hhmm"]
    assert 0 <= meta["view_hour"] <= 23


def test_fresh_scenario_has_full_contract_shape(monkeypatch):
    ts = "2026-01-12T14:30:00+00:00"
    _patch(
        monkeypatch,
        nws_inputs={"snow_inches": 3.0, "start_hour": 5, "duration_hours": 4,
                    "stale_since": None},
        nws_fetched=ts,
        mbta_flags_val={"green_e_suspended": False, "elevators_out": [],
                        "stale_since": None},
        mbta_fetched=ts,
    )
    scenario, _meta = live_scenario()
    assert set(scenario.keys()) == {
        "snow_inches", "start_hour", "duration_hours",
        "parking_compliance", "green_e_suspended", "elevators_out",
    }


# ------------------------------------------------------------------ stale path


def test_stale_fallback_surfaces_data_as_of_timestamp(monkeypatch):
    # Both sources fell back to a snapshot: stale_since set, fetched_at == snapshot.
    snap_ts = "2026-01-12T09:15:00+00:00"
    _patch(
        monkeypatch,
        nws_inputs={"snow_inches": 12.0, "start_hour": 6, "duration_hours": 12,
                    "stale_since": snap_ts},
        nws_fetched=snap_ts,
        mbta_flags_val={"green_e_suspended": True, "elevators_out": ["place-longw"],
                        "stale_since": snap_ts},
        mbta_fetched=snap_ts,
    )
    scenario, meta = live_scenario()

    # Values still flow through from the snapshot.
    assert scenario["snow_inches"] == 12.0
    assert scenario["green_e_suspended"] is True

    # Requirement 8.4: stale is flagged and carries its timestamp.
    assert meta["nws"]["fresh"] is False
    assert meta["mbta"]["fresh"] is False
    assert meta["any_stale"] is True
    assert meta["no_live_data"] is False
    assert meta["nws"]["stale_since"] == snap_ts
    assert meta["data_as_of"] == snap_ts
    # "data as of HH:MM" is the local rendering of that snapshot time.
    expected_hhmm = datetime.fromisoformat(snap_ts).astimezone().strftime("%H:%M")
    assert meta["data_as_of_hhmm"] == expected_hhmm


def test_mixed_freshness_marks_any_stale_and_uses_oldest(monkeypatch):
    # NWS fresh (now), MBTA stale (earlier snapshot). any_stale must be True and
    # the "data as of" must reflect the older MBTA snapshot, not the fresh fetch.
    fresh_ts = "2026-01-12T14:30:00+00:00"
    stale_ts = "2026-01-12T08:00:00+00:00"
    _patch(
        monkeypatch,
        nws_inputs={"snow_inches": 5.0, "start_hour": 7, "duration_hours": 6,
                    "stale_since": None},
        nws_fetched=fresh_ts,
        mbta_flags_val={"green_e_suspended": False, "elevators_out": [],
                        "stale_since": stale_ts},
        mbta_fetched=stale_ts,
    )
    _scenario, meta = live_scenario()

    assert meta["nws"]["fresh"] is True
    assert meta["mbta"]["fresh"] is False
    assert meta["any_stale"] is True
    # Oldest/most-relevant timestamp wins so we never over-state freshness.
    assert meta["data_as_of"] == stale_ts


# ------------------------------------------------------------------ never raises


def test_adapter_exception_falls_back_to_safe_default(monkeypatch):
    # Even though adapters promise not to raise, the aggregator must survive if
    # one ever does. It returns a calm scenario flagged no_live_data.
    def boom(*a, **k):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(live, "nws_storm_inputs", boom)
    monkeypatch.setattr(
        live, "mbta_flags",
        lambda *a, **k: ({"green_e_suspended": False, "elevators_out": [],
                          "stale_since": None}, "2026-01-12T14:30:00+00:00"),
    )

    scenario, meta = live_scenario()
    assert meta["no_live_data"] is True
    assert meta["any_stale"] is True
    assert scenario["snow_inches"] == 0.0
    assert scenario["green_e_suspended"] is False
    assert scenario["parking_compliance"] == DEFAULT_PARKING_COMPLIANCE
    assert 0 <= meta["view_hour"] <= 23
