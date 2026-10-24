"""Plain-language resident messages for a recommended trip. Owner: D (demo & params).

This is the D-owned ``src/outputs/messages.py`` named in design.md's file-ownership
table. It turns one ``TripResult`` (see ``src/contract.py``) into a short, calm,
plain-language message a resident can read on a phone (Requirement 11.3).

The rules live in ``.kiro/steering/privacy-and-messages.md`` and are implemented
here exactly:

  * At most 320 characters. Plain words, no jargon.
  * Order: what changed -> when to leave -> how -> time saved.
  * Always include a clock time ("Leave by 8:55").
  * Never recommend an option the planner marked infeasible for this person
    (Requirement 13.3). A broken / unroutable trip says so and offers a safe
    fallback (reschedule, call the destination, The RIDE) instead of telling
    someone to drive into a storm.
  * Rideshare prices are always "about $X-$Y", never a single quoted price.
  * No alarmist language. Calm, specific, kind.

The whole thing is **template-first**: no LLM is needed to produce a correct
message. ``compose_message`` builds the string from a fixed template and then
runs ``check_message`` on it, so every message this module returns is guaranteed
to satisfy the hard rules (length and a clock time) before it leaves the function.

Privacy (Requirement 13): this module only ever handles a place *label* and
times. It stores nothing, logs nothing, and never sees a medical reason.

Depends only on the standard library.
"""

from __future__ import annotations

from datetime import datetime, time
import re
from typing import Mapping, Sequence

# The hard limit from the steering file and Requirement 11.3.
MAX_CHARS = 320

# A clock time like "8:55", "08:55", "9:05 am", "10:00". Used by the checker to
# guarantee every message tells the reader a concrete time to act on.
_CLOCK_RE = re.compile(r"\b\d{1,2}:\d{2}\s?(?:am|pm)?\b", re.IGNORECASE)

# Words that read as alarmist / jargon-y. Kept small and specific; the checker
# only *warns* on these so a legitimate label is never blocked, but the
# templates below avoid them on purpose.
_ALARMIST = ("alert", "warning", "danger", "severe", "emergency", "severity")

# Safe fallbacks offered when a trip can't be made as usual (Requirement 5.5 /
# 13.3). Plain language, no option the planner rejected.
_FALLBACKS = "reschedule, call ahead, or book The RIDE"


def _fmt_clock(value) -> str:
    """Format a time as a plain ``H:MM`` clock string (no leading zero on hour).

    Accepts a ``datetime``/``time`` or an already-formatted ``str`` (e.g.
    "8:55"). Strings are returned trimmed so callers can pass a hand-written
    time; datetimes are rendered in local wall-clock form.
    """
    if isinstance(value, (datetime, time)):
        hour = value.hour % 12 or 12
        return f"{hour}:{value.minute:02d}"
    return str(value).strip()


def _normalize_mode(mode_summary: str) -> str:
    """A short, lowercase-friendly phrase for *how* to travel.

    ``mode_summary`` is expected to already be plain language from the caller,
    e.g. "the 39 bus from your corner" or "a ride (about $12-$18)". This just
    trims it and strips a trailing period so the template controls punctuation.
    """
    return (mode_summary or "").strip().rstrip(".")


def format_price_range(low: float, high: float) -> str:
    """Render a rideshare cost as ``about $X-$Y`` (Requirement 10.3 / steering).

    Never produces a single quoted price: if ``low == high`` the range collapses
    but the phrasing stays "about $X-$Y" with the same value on both sides, so a
    reader never mistakes an estimate for a fixed fare.
    """
    lo = max(0, round(float(low)))
    hi = max(lo, round(float(high)))
    return f"about ${lo}-${hi}"


def check_message(msg: str) -> list[str]:
    """Return a list of rule violations for ``msg``; empty means it passes.

    Deterministic checker for the two **hard** rules from the steering file and
    Requirement 11.3:

      * over ``MAX_CHARS`` (320) characters, and
      * missing a clock time the reader can act on.

    Alarmist wording is reported too, so templates can be kept calm, but note
    that ``compose_message`` only asserts on the hard rules (length + clock) to
    avoid ever blocking a legitimate place label that happens to contain a
    flagged word.
    """
    violations: list[str] = []
    text = msg or ""

    if len(text) > MAX_CHARS:
        violations.append(f"too long: {len(text)} chars (max {MAX_CHARS})")

    if not _CLOCK_RE.search(text):
        violations.append("missing a clock time (e.g. 'Leave by 8:55')")

    lowered = text.lower()
    for word in _ALARMIST:
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            violations.append(f"alarmist/jargon word: '{word}'")

    return violations


def _hard_violations(msg: str) -> list[str]:
    """Only the hard rules (length + clock) that ``compose_message`` guarantees."""
    return [v for v in check_message(msg) if "alarmist" not in v]


def compose_message(
    trip_result: Mapping,
    *,
    trip_label: str,
    leave_by_hhmm,
    mode_summary: str,
    time_saved_min: float | None = None,
    warnings: Sequence[str] | None = None,
    persona: Mapping | None = None,
) -> str:
    """Compose a plain-language resident message from a ``TripResult``.

    Template-first (no LLM). The output is guaranteed to pass the hard checks in
    ``check_message`` (<= 320 chars, contains a clock time) before it is
    returned; if the template somehow overflows, the time-saved tail is trimmed
    first, then warnings, so the essential "what / when / how" always survives.

    Args:
      trip_result: a ``TripResult``-shaped mapping (see ``src/contract.py``).
        Only ``broken``, ``minutes`` and ``warnings`` are read. A broken or
        unroutable trip (``broken`` true or non-finite ``minutes``) produces a
        fallback message and never recommends the normal option (Requirement
        13.3 / 5.5).
      trip_label: the destination's place label, e.g. "Brigham pharmacy".
        A label only, never a medical reason (Requirement 4.3 / 13).
      leave_by_hhmm: the recommended departure, as a ``datetime``/``time`` or a
        pre-formatted clock string like "8:55".
      mode_summary: plain-language *how* to travel, e.g. "the 39 bus from your
        corner". Rideshare costs, if included, must already be a range from
        ``format_price_range`` ("about $12-$18").
      time_saved_min: minutes saved vs the usual way under the same storm
        (Requirement 7.2). Omitted or <= 0 -> no time-saved sentence.
      warnings: extra plain-language notes to surface (e.g. an elevator outage).
        Falls back to ``trip_result['warnings']`` when not given.
      persona: optional persona mapping; reserved for future tailoring (e.g.
        step-free wording). Not required for a correct message.

    Returns:
      The finished message string (<= 320 chars, with a clock time).

    Raises:
      AssertionError: if the composed message still fails a hard rule after
        trimming. This is a guardrail: it should never fire for normal inputs.
    """
    label = (trip_label or "your trip").strip() or "your trip"
    clock = _fmt_clock(leave_by_hhmm)
    notes = list(warnings) if warnings is not None else list(trip_result.get("warnings") or [])

    broken = bool(trip_result.get("broken"))
    minutes = trip_result.get("minutes")
    unroutable = minutes is None or minutes == float("inf")

    # ---- Broken / unroutable trip: a safe fallback, never "drive into it" ----
    if broken or unroutable:
        # What changed (calm) -> what to do instead. No clock-time departure is
        # meaningful here, so we anchor the required clock time on the deadline
        # wording the caller passed, if any, and otherwise keep the fallback.
        head = f"Getting to {label} is hard in today's storm"
        if notes:
            head += f" ({notes[0].rstrip('.').lower()})"
        body = (
            f". There isn't a safe way we'd recommend right now. "
            f"Best options: {_FALLBACKS}."
        )
        # Guarantee a clock time is present so the checker passes and the reader
        # has a concrete anchor (the time they planned to leave / be there).
        tail = f" You'd planned to leave around {clock}." if _CLOCK_RE.search(clock) else ""
        msg = (head + body + tail).strip()
        msg = _enforce_hard_rules(msg, clock)
        assert not _hard_violations(msg), f"broken-trip message failed checks: {_hard_violations(msg)}"
        return msg

    # ---- Normal trip: what changed -> when to leave -> how -> time saved -----
    how = _normalize_mode(mode_summary) or "your usual way"

    # "What changed": lead with the most relevant warning in plain words, else a
    # calm generic line. Never alarmist.
    if notes:
        changed = notes[0].rstrip(".")
    else:
        changed = "Snow is slowing travel today"

    when = f"For {label}, leave by {clock}"
    how_part = f"and take {how}"

    parts = [f"{changed}.", f"{when} {how_part}."]

    if time_saved_min is not None and time_saved_min > 0:
        saved = int(round(time_saved_min))
        parts.append(f"About {saved} min faster than your usual way today.")

    msg = " ".join(parts).strip()

    # Trim gracefully if we somehow exceed the limit: drop the time-saved tail
    # first, then any trailing warning detail, keeping what/when/how intact.
    if len(msg) > MAX_CHARS:
        core = f"{changed}. {when} {how_part}."
        msg = core.strip()
    if len(msg) > MAX_CHARS:
        # Last resort: keep the actionable when+how (still has the clock time).
        msg = f"{when} {how_part}.".strip()

    msg = _enforce_hard_rules(msg, clock)
    assert not _hard_violations(msg), f"message failed checks: {_hard_violations(msg)}"
    return msg


def _enforce_hard_rules(msg: str, clock: str) -> str:
    """Final safety net: ensure a clock time is present and length <= MAX_CHARS.

    ``compose_message`` is structured so this should be a no-op for real inputs,
    but it guarantees the function's contract even for odd callers.
    """
    text = msg
    if not _CLOCK_RE.search(text) and _CLOCK_RE.search(clock or ""):
        text = f"{text} Leave by {clock.strip()}.".strip()
    if len(text) > MAX_CHARS:
        text = text[: MAX_CHARS - 1].rstrip() + "."
    return text
