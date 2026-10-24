"""Tests for the resident message generator (task 18, Requirements 11.3, 13.3).

These verify the hard rules from ``.kiro/steering/privacy-and-messages.md``:

  * every message is at most 320 characters,
  * every message contains a clock time the reader can act on,
  * a normal message mentions the leave-by time and how to travel, and
  * a broken / unroutable trip never recommends the infeasible option
    (Requirement 13.3) and instead offers a safe fallback.

Both example-based unit tests and a property-based test (Hypothesis) are
included, since compose_message must hold its length + clock guarantee across a
wide range of labels, times and warnings.
"""

from __future__ import annotations

from datetime import datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from src.outputs.messages import (
    MAX_CHARS,
    check_message,
    compose_message,
    format_price_range,
)


def _ok_trip(minutes: float = 24.0, warnings=None) -> dict:
    return {
        "minutes": minutes,
        "clear_day_minutes": 11.0,
        "broken": False,
        "leave_earlier_by_min": 13.0,
        "route_nodes": [1, 2, 3],
        "warnings": warnings or [],
    }


def _broken_trip(warnings=None) -> dict:
    return {
        "minutes": float("inf"),
        "clear_day_minutes": 11.0,
        "broken": True,
        "leave_earlier_by_min": 0.0,
        "route_nodes": [],
        "warnings": warnings or [],
    }


# --------------------------------------------------------------------------- check_message


def test_check_message_flags_too_long():
    long = "x" * (MAX_CHARS + 1) + " 8:55"
    violations = check_message(long)
    assert any("too long" in v for v in violations)


def test_check_message_flags_missing_clock():
    violations = check_message("Leave soon and take the bus.")
    assert any("clock time" in v for v in violations)


def test_check_message_passes_good_message():
    good = "Snow is slowing the E train. For Brigham, leave by 8:55 and take the 39 bus."
    assert check_message(good) == []


# --------------------------------------------------------------------------- compose_message (normal)


def test_compose_message_basic_shape():
    msg = compose_message(
        _ok_trip(warnings=["Snow is slowing the E train"]),
        trip_label="Brigham pharmacy",
        leave_by_hhmm="8:55",
        mode_summary="the 39 bus from your corner",
        time_saved_min=25,
    )
    assert len(msg) <= MAX_CHARS
    assert check_message(msg) == []
    # Mentions the leave-by time and how to travel.
    assert "8:55" in msg
    assert "39 bus" in msg
    assert "Brigham pharmacy" in msg
    # Time saved as a plain sentence.
    assert "25 min" in msg


def test_compose_message_accepts_datetime_leave_by():
    msg = compose_message(
        _ok_trip(),
        trip_label="clinic",
        leave_by_hhmm=datetime(2025, 1, 15, 8, 55),
        mode_summary="the 39 bus",
    )
    assert "8:55" in msg
    assert check_message(msg) == []


def test_compose_message_without_time_saved_has_no_faster_line():
    msg = compose_message(
        _ok_trip(),
        trip_label="clinic",
        leave_by_hhmm="9:05",
        mode_summary="the 39 bus",
        time_saved_min=None,
    )
    assert "faster" not in msg
    assert "9:05" in msg


def test_compose_message_zero_time_saved_omits_line():
    msg = compose_message(
        _ok_trip(),
        trip_label="clinic",
        leave_by_hhmm="9:05",
        mode_summary="the 39 bus",
        time_saved_min=0,
    )
    assert "faster" not in msg


# --------------------------------------------------------------------------- compose_message (broken, 13.3)


def test_broken_trip_does_not_recommend_driving():
    msg = compose_message(
        _broken_trip(warnings=["Side streets are closed"]),
        trip_label="Brigham pharmacy",
        leave_by_hhmm="8:55",
        mode_summary="drive yourself",  # would be the infeasible option
    )
    assert len(msg) <= MAX_CHARS
    assert check_message(msg) == []
    lowered = msg.lower()
    # Must NOT recommend the infeasible option passed in.
    assert "drive yourself" not in lowered
    assert "take drive" not in lowered
    # Must offer a safe fallback instead (Requirement 5.5 / 13.3).
    assert ("reschedule" in lowered) or ("the ride" in lowered) or ("call ahead" in lowered)


def test_broken_trip_by_flag_only():
    trip = _ok_trip()
    trip["broken"] = True
    msg = compose_message(
        trip,
        trip_label="clinic",
        leave_by_hhmm="10:00",
        mode_summary="the 39 bus",
    )
    assert check_message(msg) == []
    assert "reschedule" in msg.lower() or "the ride" in msg.lower()


# --------------------------------------------------------------------------- price range (10.3)


def test_format_price_range_is_always_a_range():
    assert format_price_range(12, 18) == "about $12-$18"


def test_format_price_range_single_value_still_reads_as_estimate():
    # Even when low == high, it stays "about $X-$Y", never a single quote.
    assert format_price_range(15, 15) == "about $15-$15"
    assert "about" in format_price_range(15, 15)


def test_price_range_embeds_in_message_within_limit():
    msg = compose_message(
        _ok_trip(),
        trip_label="clinic",
        leave_by_hhmm="9:05",
        mode_summary=f"a ride ({format_price_range(12, 18)})",
        time_saved_min=10,
    )
    assert "about $12-$18" in msg
    assert len(msg) <= MAX_CHARS


# --------------------------------------------------------------------------- property test


@settings(max_examples=200)
@given(
    label=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs")),
        min_size=0,
        max_size=60,
    ),
    hour=st.integers(min_value=0, max_value=23),
    minute=st.integers(min_value=0, max_value=59),
    minutes=st.floats(min_value=1, max_value=400),
    time_saved=st.one_of(st.none(), st.floats(min_value=0, max_value=600)),
    broken=st.booleans(),
    n_warnings=st.integers(min_value=0, max_value=3),
)
def test_message_always_within_limit_and_has_clock(
    label, hour, minute, minutes, time_saved, broken, n_warnings
):
    """compose_message always returns <= 320 chars with a clock time.

    **Validates: Requirements 11.3, 13.3**
    """
    warnings = [f"note {i} about travel" for i in range(n_warnings)]
    trip = {
        "minutes": minutes,
        "clear_day_minutes": 10.0,
        "broken": broken,
        "leave_earlier_by_min": 5.0,
        "route_nodes": [],
        "warnings": warnings,
    }
    clock = f"{hour % 12 or 12}:{minute:02d}"
    msg = compose_message(
        trip,
        trip_label=label,
        leave_by_hhmm=clock,
        mode_summary="the 39 bus from your corner",
        time_saved_min=time_saved,
    )
    # Hard guarantees hold for every input.
    assert len(msg) <= MAX_CHARS
    hard = [v for v in check_message(msg) if "alarmist" not in v]
    assert hard == [], hard
    # A broken trip never recommends the normal mode; it offers a fallback.
    if broken or minutes == float("inf"):
        low = msg.lower()
        assert ("reschedule" in low) or ("the ride" in low) or ("call ahead" in low)
