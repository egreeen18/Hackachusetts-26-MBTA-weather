"""Live-scenario aggregator for the "Live now" button. Owner: A.

Task 15: combine the two live adapters into one contract-shaped Scenario plus a
small freshness report the UI can show:

    live_scenario() -> (scenario, meta)

- NWS (``nws_storm_inputs``) fills ``snow_inches``, ``start_hour``,
  ``duration_hours``.
- MBTA (``mbta_flags``) fills ``green_e_suspended`` and ``elevators_out``.
- ``parking_compliance`` is NOT a live signal, so it defaults to a sensible
  value (``DEFAULT_PARKING_COMPLIANCE``).

Freshness (Requirement 8.4): each adapter reports ``stale_since`` — ``None`` when
the value came from a live fetch, or a timestamp when it fell back to the last
saved snapshot. ``meta`` surfaces, per source, whether it is fresh or stale, and
a single combined "data as of HH:MM" string for the caption. Every live poll
still writes a snapshot inside the adapters (Requirement 8.5); this aggregator
does not disable that.

Both adapters already promise never to raise; this aggregator keeps that promise
too. If something unexpected happens and no live data is available, it returns a
safe default scenario and a ``meta`` marked ``no_live_data`` so the UI can say so.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional, TypedDict

from src.adapters.mbta import mbta_flags
from src.adapters.nws import nws_storm_inputs
from src.contract import Scenario

log = logging.getLogger("adapters.live")

# parking_compliance has no live feed (no sensor tells us how many cars moved off
# the snow-emergency routes), so the live scenario uses the same middle-of-the-road
# default the sliders start at. See src/contract.py DEFAULT_SCENARIO.
DEFAULT_PARKING_COMPLIANCE = 0.6


class SourceMeta(TypedDict):
    """Freshness of one live source (Requirement 8.4)."""
    fresh: bool                 # True = live fetch, False = fell back to snapshot
    fetched_at: str             # ISO8601 time this value was obtained
    stale_since: Optional[str]  # ISO8601 snapshot timestamp if stale, else None


class LiveMeta(TypedDict):
    """What the UI needs to caption a live run."""
    nws: SourceMeta
    mbta: SourceMeta
    any_stale: bool             # True if either source is on snapshot data
    no_live_data: bool          # True only in the safe-default fallback
    data_as_of: str             # ISO8601 of the oldest/most-relevant timestamp
    data_as_of_hhmm: str        # "HH:MM" for the caption
    view_hour: int              # hour of day the UI should render (0-23)


def _source_meta(fetched_at: str, stale_since: Optional[str]) -> SourceMeta:
    """Build a SourceMeta from an adapter's (fetched_at, stale_since).

    An adapter sets ``stale_since`` only when it served a snapshot, so
    ``fresh`` is simply "no stale marker".
    """
    return {
        "fresh": stale_since is None,
        "fetched_at": fetched_at,
        "stale_since": stale_since,
    }


def _hhmm(iso_ts: str) -> str:
    """Format an ISO8601 timestamp as local wall-clock ``HH:MM`` for display.

    The adapters record UTC timestamps; we convert to the machine's local time
    so the caption matches the user's clock. Falls back to the raw string if it
    cannot be parsed (never raises — this is display-only).
    """
    try:
        dt = datetime.fromisoformat(iso_ts)
        if dt.tzinfo is not None:
            dt = dt.astimezone()  # to local time
        return dt.strftime("%H:%M")
    except (ValueError, TypeError):
        return iso_ts


def _as_of(nws: SourceMeta, mbta: SourceMeta) -> str:
    """Pick the timestamp to show as "data as of".

    The caption should reflect the *least fresh* data on screen, so the user is
    never told conditions are newer than they are. We take the older of the two
    relevant timestamps: a source's ``stale_since`` when stale, else its
    ``fetched_at``.
    """
    nws_ts = nws["stale_since"] or nws["fetched_at"]
    mbta_ts = mbta["stale_since"] or mbta["fetched_at"]
    # String compare is valid for ISO8601 in the same offset; fall back safely.
    try:
        return min(nws_ts, mbta_ts, key=lambda t: datetime.fromisoformat(t))
    except (ValueError, TypeError):
        return min(nws_ts, mbta_ts)


def _view_hour(nws_inputs: dict) -> int:
    """Choose the hour of day the UI should render for live conditions.

    Live means "right now", so default to the current local hour. If the forecast
    says the snow has not started yet (current hour is before ``start_hour`` on
    the same day) we still view the current hour — the map shows conditions now,
    and the user can scrub forward with the slider. Clamped to 0-23.
    """
    hour = datetime.now().hour
    return max(0, min(23, hour))


def _safe_default() -> tuple[Scenario, LiveMeta]:
    """Fallback when nothing live (and no snapshot) is available.

    Returns a calm, no-storm scenario and a meta clearly flagged ``no_live_data``
    so the UI can tell the user it is not showing live conditions.
    """
    now = datetime.now(timezone.utc).isoformat()
    scenario: Scenario = {
        "snow_inches": 0.0,
        "start_hour": 0,
        "duration_hours": 0,
        "parking_compliance": DEFAULT_PARKING_COMPLIANCE,
        "green_e_suspended": False,
        "elevators_out": [],
    }
    empty: SourceMeta = {"fresh": False, "fetched_at": now, "stale_since": now}
    meta: LiveMeta = {
        "nws": empty,
        "mbta": dict(empty),  # type: ignore[typeddict-item]
        "any_stale": True,
        "no_live_data": True,
        "data_as_of": now,
        "data_as_of_hhmm": _hhmm(now),
        "view_hour": max(0, min(23, datetime.now().hour)),
    }
    return scenario, meta


def live_scenario() -> tuple[Scenario, LiveMeta]:
    """Build a contract-shaped Scenario from the live NWS + MBTA adapters.

    Returns ``(scenario, meta)``. Never raises: the underlying adapters already
    guarantee this, and any unexpected error here falls back to a safe default
    scenario with ``meta["no_live_data"] == True``.

    See the module docstring for the freshness semantics (Requirement 8.4) and
    the snapshot guarantee (Requirement 8.5, provided by the adapters).
    """
    try:
        nws_inputs, nws_fetched = nws_storm_inputs()
        mbta_fl, mbta_fetched = mbta_flags()

        scenario: Scenario = {
            "snow_inches": float(nws_inputs.get("snow_inches", 0.0)),
            "start_hour": int(nws_inputs.get("start_hour", 0)),
            "duration_hours": int(nws_inputs.get("duration_hours", 0)),
            "parking_compliance": DEFAULT_PARKING_COMPLIANCE,
            "green_e_suspended": bool(mbta_fl.get("green_e_suspended", False)),
            "elevators_out": list(mbta_fl.get("elevators_out", []) or []),
        }

        nws_meta = _source_meta(nws_fetched, nws_inputs.get("stale_since"))
        mbta_meta = _source_meta(mbta_fetched, mbta_fl.get("stale_since"))
        data_as_of = _as_of(nws_meta, mbta_meta)

        meta: LiveMeta = {
            "nws": nws_meta,
            "mbta": mbta_meta,
            "any_stale": not (nws_meta["fresh"] and mbta_meta["fresh"]),
            "no_live_data": False,
            "data_as_of": data_as_of,
            "data_as_of_hhmm": _hhmm(data_as_of),
            "view_hour": _view_hour(nws_inputs),
        }
        log.info(
            "live scenario: snow_inches=%s e_suspended=%s elevators_out=%d "
            "nws_fresh=%s mbta_fresh=%s view_hour=%s",
            scenario["snow_inches"], scenario["green_e_suspended"],
            len(scenario["elevators_out"]), nws_meta["fresh"], mbta_meta["fresh"],
            meta["view_hour"],
        )
        return scenario, meta
    except Exception as e:  # defensive: aggregator must never raise to the UI
        log.warning("live_scenario fell back to safe default (%s)",
                    e.__class__.__name__)
        return _safe_default()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
    scenario, meta = live_scenario()
    print("scenario:", scenario)
    print("data as of:", meta["data_as_of_hhmm"],
          "(stale)" if meta["any_stale"] else "(fresh)")
    print("view hour:", meta["view_hour"])


if __name__ == "__main__":
    main()
