"""Tests for the trip .ics export (task 17, Requirement 11.1 / 4.3).

Covers that ``build_trip_ics`` produces valid iCalendar bytes with a VEVENT and
a "Leave by" summary, that a VALARM reminder is attached, and that
``compute_leave_by`` subtracts travel time (and buffer) from the deadline and
degrades gracefully for an unroutable trip. Privacy: no reason field feeds this
and we never put one in the output.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from icalendar import Calendar

from src.outputs.ics import build_trip_ics, compute_leave_by


def _sample_times():
    arrive = datetime(2025, 1, 15, 9, 0)
    leave = datetime(2025, 1, 15, 8, 30)
    return leave, arrive


# --------------------------------------------------------------------------- build_trip_ics


def test_build_trip_ics_returns_bytes():
    leave, arrive = _sample_times()
    data = build_trip_ics("Brigham pharmacy", leave, arrive)
    assert isinstance(data, bytes)
    assert len(data) > 0


def test_ics_contains_vevent_and_leave_by():
    leave, arrive = _sample_times()
    data = build_trip_ics("Brigham pharmacy", leave, arrive)
    text = data.decode("utf-8")
    assert "BEGIN:VEVENT" in text
    assert "Leave by" in text
    # The leave-by time (08:30) appears in the summary.
    assert "08:30" in text


def test_ics_parses_and_has_leave_by_event():
    leave, arrive = _sample_times()
    cal = Calendar.from_ical(build_trip_ics("Brigham pharmacy", leave, arrive))
    events = [c for c in cal.walk("VEVENT")]
    # Two events: the leave-by reminder and the travel block.
    assert len(events) == 2
    summaries = [str(e.get("summary")) for e in events]
    assert any(s.startswith("Leave by") for s in summaries)
    assert any(s.startswith("Travel to") for s in summaries)


def test_ics_has_valarm_reminder():
    leave, arrive = _sample_times()
    cal = Calendar.from_ical(build_trip_ics("Brigham pharmacy", leave, arrive))
    alarms = [c for c in cal.walk("VALARM")]
    assert len(alarms) == 1
    # Fires 15 minutes before by default (negative trigger).
    trigger = alarms[0].get("trigger")
    assert trigger.dt == timedelta(minutes=-15)


def test_ics_label_only_no_reason_leaks():
    # The label is the only free text about the destination; a reason never
    # reaches this function, so it can't appear in the output.
    leave, arrive = _sample_times()
    text = build_trip_ics("Brigham pharmacy", leave, arrive,
                          summary="Storm trip 24 min vs 11 min clear day.").decode("utf-8")
    assert "Brigham pharmacy" in text
    assert "diagnosis" not in text.lower()
    assert "reason" not in text.lower()


def test_ics_handles_empty_label():
    leave, arrive = _sample_times()
    data = build_trip_ics("", leave, arrive)
    assert b"BEGIN:VEVENT" in data
    assert b"Leave by" in data


# --------------------------------------------------------------------------- compute_leave_by


def test_compute_leave_by_subtracts_travel_time():
    arrive = datetime(2025, 1, 15, 9, 0)
    leave = compute_leave_by(arrive, storm_minutes=25.0)
    assert leave == datetime(2025, 1, 15, 8, 35)


def test_compute_leave_by_adds_safety_buffer():
    arrive = datetime(2025, 1, 15, 9, 0)
    leave = compute_leave_by(arrive, storm_minutes=25.0, safety_buffer_min=20.0)
    assert leave == datetime(2025, 1, 15, 8, 15)


def test_compute_leave_by_unroutable_returns_arrive_by():
    arrive = datetime(2025, 1, 15, 9, 0)
    leave = compute_leave_by(arrive, storm_minutes=float("inf"))
    assert leave == arrive
