"""MBTA live-alert adapter. Owner: A.

Task 5.2: mbta_flags() -> {"green_e_suspended": bool, "elevators_out": [...]}
from live MBTA alerts (SUSPENSION/SHUTTLE on Green-E; ELEVATOR_CLOSURE at
study-area stops). Tested against saved fixtures. (Requirements 8.1, 8.2)

These flags fill the Scenario dict defined in src/contract.py:
    green_e_suspended -> more cars on Huntington Ave (B's simulator)
    elevators_out     -> stop ids with a closed elevator (trip_time warnings)

Adapter rules (steering/data-sources.md, tech.md):
  - Return (result, fetched_at); never raise to callers.
  - On failure, use the last snapshot and set stale_since.
  - Save one real response per endpoint in tests/fixtures/; test against it.
  - Log endpoint names and counts only, never persona data.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = PROJECT_ROOT / "data" / "snapshots"
MBTA_SNAPSHOT = SNAPSHOT_DIR / "mbta_flags_latest.json"

MBTA = "https://api-v3.mbta.com"
TIMEOUT = 10.0

# Effects (MBTA alert `effect` values) that take the Green-E branch out of
# normal service.
E_SUSPENSION_EFFECTS = {"SUSPENSION", "SHUTTLE", "STATION_CLOSURE", "STOP_CLOSURE"}
GREEN_E = "Green-E"

log = logging.getLogger("adapters.mbta")


def _mbta_headers() -> dict[str, str]:
    key = os.environ.get("MBTA_API_KEY")
    return {"x-api-key": key} if key else {}


# ------------------------------------------------------------------ parsing

def _informed_entities(alert: dict) -> list[dict]:
    """Return informed_entity list from either a raw JSON:API alert object or
    the flattened shape the boston-civic MCP tool emits."""
    attrs = alert.get("attributes", alert)
    return attrs.get("informed_entity", []) or []


def _effect(alert: dict) -> str | None:
    return alert.get("attributes", alert).get("effect")


def parse_flags(alerts: Iterable[dict], study_area_stops: set[str] | None = None) -> dict:
    """Pure function: turn a list of MBTA alerts into the flags dict.

    Separated from I/O so it can be unit-tested against saved fixtures without
    any network access.

    study_area_stops: if given, only elevator closures at these stop ids count;
    if None, every ELEVATOR_CLOSURE stop is included (the caller filters to the
    bbox via the transit cache).
    """
    green_e_suspended = False
    elevators_out: list[str] = []

    for alert in alerts:
        effect = _effect(alert)
        entities = _informed_entities(alert)
        routes = {e.get("route") for e in entities if e.get("route")}
        stops = {e.get("stop") for e in entities if e.get("stop")}

        if effect in E_SUSPENSION_EFFECTS and GREEN_E in routes:
            green_e_suspended = True

        if effect == "ELEVATOR_CLOSURE":
            for stop in stops:
                if study_area_stops is None or stop in study_area_stops:
                    if stop not in elevators_out:
                        elevators_out.append(stop)

    return {"green_e_suspended": green_e_suspended, "elevators_out": elevators_out}


# ------------------------------------------------------------------ fetch

def _fetch_alerts(routes: str = "Green-D,Green-E") -> list[dict]:
    r = httpx.get(
        f"{MBTA}/alerts",
        params={"filter[route]": routes, "filter[activity]": "ALL"},
        headers=_mbta_headers(),
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json().get("data", [])


def _save_snapshot(flags: dict, fetched_at: str) -> None:
    try:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        MBTA_SNAPSHOT.write_text(
            json.dumps({"flags": flags, "fetched_at": fetched_at}, indent=2),
            encoding="utf-8",
        )
    except OSError as e:  # never let snapshot I/O break the caller
        log.warning("mbta snapshot write failed: %s", e.__class__.__name__)


def _load_snapshot() -> tuple[dict, str] | None:
    if not MBTA_SNAPSHOT.exists():
        return None
    try:
        obj = json.loads(MBTA_SNAPSHOT.read_text(encoding="utf-8"))
        return obj["flags"], obj["fetched_at"]
    except (OSError, ValueError, KeyError):
        return None


def mbta_flags(study_area_stops: set[str] | None = None) -> tuple[dict, str]:
    """Live MBTA flags for the study area.

    Returns (flags, fetched_at) where flags is:
        {"green_e_suspended": bool, "elevators_out": [stop_id, ...],
         "stale_since": <iso8601> | None}

    On any network/parse failure, falls back to the last saved snapshot and sets
    stale_since to that snapshot's timestamp. If there is no snapshot either,
    returns empty flags with stale_since = now so the UI can say "no live data".
    Never raises.
    """
    try:
        alerts = _fetch_alerts()
        flags = parse_flags(alerts, study_area_stops)
        fetched_at = datetime.now(timezone.utc).isoformat()
        flags["stale_since"] = None
        log.info("mbta /alerts ok: %d alerts, e_suspended=%s, %d elevators out",
                 len(alerts), flags["green_e_suspended"], len(flags["elevators_out"]))
        _save_snapshot(flags, fetched_at)
        return flags, fetched_at
    except (httpx.HTTPError, ValueError) as e:
        log.warning("mbta /alerts failed (%s); using last snapshot",
                    e.__class__.__name__)
        snap = _load_snapshot()
        if snap is not None:
            flags, fetched_at = snap
            flags["stale_since"] = fetched_at
            return flags, fetched_at
        now = datetime.now(timezone.utc).isoformat()
        return {"green_e_suspended": False, "elevators_out": [],
                "stale_since": now}, now


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
    flags, fetched_at = mbta_flags()
    print(f"fetched_at: {fetched_at}")
    print(f"green_e_suspended: {flags['green_e_suspended']}")
    print(f"elevators_out: {flags['elevators_out']}")
    print(f"stale_since: {flags['stale_since']}")


if __name__ == "__main__":
    main()
