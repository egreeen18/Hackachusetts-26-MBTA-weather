"""Calendar (.ics) export for a persona's trip. Owner: C (UI & map).

This is the C-owned ``src/outputs/ics.py`` named in design.md's file-ownership
table. It turns one recommended trip into an iCalendar file the traveller can
drop into their own calendar app (Requirement 11.1):

  * a "Leave by HH:MM" event at the recommended departure time, and
  * a travel block from that departure to the arrival deadline,
  * with a VALARM 15 minutes before "Leave by" so the phone nudges them.

``build_trip_ics(...)`` returns raw ``bytes`` (a serialized VCALENDAR) so the
caller can hand it straight to Streamlit's ``st.download_button`` without
touching the filesystem.

Privacy (Requirement 13): the .ics carries only a place *label* and the times.
No medical reason, no diagnosis, no home address is ever written here — the form
that feeds this never collects one. Nothing in this module logs its inputs.

Only depends on the ``icalendar`` library (already a project dependency); it does
not reach into the simulator or any other module.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from icalendar import Alarm, Calendar, Event

# Product id advertised in the VCALENDAR header (identifies the generator).
PRODID = "-//Storm Twin//Longwood & Fenway trip//EN"
ICAL_VERSION = "2.0"

# How long before "Leave by" the reminder fires (design.md: a VALARM 15 min
# before is a nice touch).
LEAVE_REMINDER_MIN = 15


def _fmt_hhmm(dt: datetime) -> str:
    """Local wall-clock ``HH:MM`` for a datetime, for human-readable summaries."""
    return dt.strftime("%H:%M")


def build_trip_ics(
    trip_label: str,
    leave_by_dt: datetime,
    arrive_by_dt: datetime,
    summary: str = "",
    *,
    reminder_min: int = LEAVE_REMINDER_MIN,
) -> bytes:
    """Build an iCalendar (.ics) file for one trip and return it as bytes.

    Produces a VCALENDAR with two VEVENTs (Requirement 11.1):

      1. **"Leave by HH:MM: <trip_label>"** — a short event pinned to
         ``leave_by_dt`` (the recommended departure). It carries a VALARM that
         fires ``reminder_min`` minutes before, so the traveller gets a nudge.
      2. **The travel block** — an event spanning ``leave_by_dt`` ->
         ``arrive_by_dt`` representing the journey itself, so the calendar shows
         the whole trip occupied, not just a point reminder.

    Args:
      trip_label: the destination's place label (e.g. "Brigham pharmacy").
        A label only — never a medical reason (Requirement 4.3 / 13).
      leave_by_dt: recommended departure time (see ``compute_leave_by`` or the
        "My trips" tab for how this is derived from arrive-by minus storm time).
      arrive_by_dt: the arrival deadline the traveller wants to make.
      summary: optional extra context appended to the travel block's
        description (e.g. "Storm trip 24 min vs 11 min clear day"). Kept factual;
        no private data.
      reminder_min: minutes before "Leave by" to fire the alarm (default 15).

    Returns:
      The serialized calendar as ``bytes`` (UTF-8), ready for a download button
      or writing to a ``.ics`` file.
    """
    label = (trip_label or "trip").strip() or "trip"

    cal = Calendar()
    cal.add("prodid", PRODID)
    cal.add("version", ICAL_VERSION)
    cal.add("method", "PUBLISH")

    leave_summary = f"Leave by {_fmt_hhmm(leave_by_dt)}: {label}"

    # --- Event 1: the "Leave by" reminder, with a VALARM ---------------------
    leave_event = Event()
    leave_event.add("summary", leave_summary)
    leave_event.add("dtstart", leave_by_dt)
    # A short 5-minute window so it shows as a block, not a zero-length instant
    # (some calendar clients hide zero-length events).
    leave_event.add("dtend", leave_by_dt + timedelta(minutes=5))
    leave_event.add("dtstamp", datetime.now())
    leave_event.add(
        "uid",
        f"stormtwin-leaveby-{leave_by_dt.strftime('%Y%m%dT%H%M%S')}@storm-twin",
    )
    leave_desc = f"Storm Twin recommendation. Arrive by {_fmt_hhmm(arrive_by_dt)}."
    if summary:
        leave_desc += f" {summary}"
    leave_desc += " Simulation estimate."
    leave_event.add("description", leave_desc)

    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("description", leave_summary)
    alarm.add("trigger", timedelta(minutes=-abs(reminder_min)))
    leave_event.add_component(alarm)

    cal.add_component(leave_event)

    # --- Event 2: the travel block ------------------------------------------
    travel_event = Event()
    travel_event.add("summary", f"Travel to {label}")
    travel_event.add("dtstart", leave_by_dt)
    travel_event.add("dtend", arrive_by_dt)
    travel_event.add("dtstamp", datetime.now())
    travel_event.add(
        "uid",
        f"stormtwin-travel-{leave_by_dt.strftime('%Y%m%dT%H%M%S')}@storm-twin",
    )
    travel_desc = "Travel block for this trip under current storm conditions."
    if summary:
        travel_desc += f" {summary}"
    travel_desc += " Simulation estimate."
    travel_event.add("description", travel_desc)

    cal.add_component(travel_event)

    return cal.to_ical()


def compute_leave_by(
    arrive_by_dt: datetime,
    storm_minutes: float,
    safety_buffer_min: float = 0.0,
) -> datetime:
    """Recommended departure = arrival deadline minus travel time (and buffer).

    The core "Leave by" rule for Requirement 11.1:

        leave_by = arrive_by - storm_minutes - safety_buffer_min

    ``storm_minutes`` is the trip's travel time under the current storm
    (``TripResult["minutes"]``). ``safety_buffer_min`` is an optional cushion the
    caller can add (the "My trips" tab exposes one); it defaults to 0 so the base
    rule stays simple and transparent.

    A non-finite ``storm_minutes`` (an unroutable trip) can't yield a meaningful
    departure time, so this returns ``arrive_by_dt`` unchanged — the caller is
    expected to show a "no route" note instead of an .ics in that case.
    """
    from math import isfinite

    if not isfinite(storm_minutes):
        return arrive_by_dt
    total = float(storm_minutes) + max(0.0, float(safety_buffer_min))
    return arrive_by_dt - timedelta(minutes=total)
