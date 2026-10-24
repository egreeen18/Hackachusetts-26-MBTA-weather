"""National Weather Service forecast adapter. Owner: A.

Task 9.2: NWS adapter turning the gridded forecast into storm-generator inputs:
    snow_inches   -> total forecast snowfall over the coming storm
    start_hour    -> local hour (0-23) the snowfall begins
    duration_hours-> number of hours snow is forecast to fall
(Requirement 8.3)

These three fields are exactly the Scenario inputs defined in src/contract.py,
so the "Live now" button (task 15) can drop them straight into a scenario dict.

NWS conventions (steering/data-sources.md):
  - Must send a User-Agent header (NWS_USER_AGENT) or requests are rejected.
  - GET /points/{lat},{lon} -> properties.forecastGridData URL.
  - Grid series (snowfallAmount, windSpeed) are lists of {validTime, value};
    validTime is "<ISO8601 start>/<ISO8601 duration>" and 'uom' gives units
    (snowfall is wmoUnit:mm; convert to inches).

Adapter rules (steering + tech.md):
  - Return (result, fetched_at); never raise to callers.
  - On failure, use the last snapshot and set stale_since.
  - Save one real response in tests/fixtures/; test the pure parser against it.
  - Log endpoint names and counts only.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = PROJECT_ROOT / "data" / "snapshots"
NWS_SNAPSHOT = SNAPSHOT_DIR / "nws_inputs_latest.json"

NWS = "https://api.weather.gov"
TIMEOUT = 10.0

# Center of the study area (Longwood Medical Area), matching mcp_server.
LONGWOOD_LAT, LONGWOOD_LON = 42.3378, -71.1050

MM_PER_INCH = 25.4

log = logging.getLogger("adapters.nws")


def _nws_headers() -> dict[str, str]:
    return {
        "User-Agent": os.environ.get("NWS_USER_AGENT", "StormTwin (set NWS_USER_AGENT)"),
        "Accept": "application/geo+json",
    }


# ------------------------------------------------------------------ duration parsing

# ISO 8601 duration limited to the day/hour forms NWS uses, e.g. PT6H, P1DT3H.
_DUR_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?)?$"
)


def _parse_duration_hours(iso_duration: str) -> float:
    """Parse an ISO 8601 duration (the part after '/') into hours."""
    m = _DUR_RE.match(iso_duration.strip())
    if not m:
        return 0.0
    days = int(m.group("days") or 0)
    hours = int(m.group("hours") or 0)
    minutes = int(m.group("minutes") or 0)
    return days * 24 + hours + minutes / 60.0


def _parse_valid_time(valid_time: str) -> tuple[datetime, float]:
    """Split a NWS validTime '<start>/<duration>' into (start_dt, hours)."""
    start_str, _, dur_str = valid_time.partition("/")
    start = datetime.fromisoformat(start_str)
    hours = _parse_duration_hours(dur_str) if dur_str else 1.0
    return start, hours


# ------------------------------------------------------------------ active alerts

# Event names (NWS 'event' field) that confirm a winter-storm product is active.
# Requirement 8.3: convert winter-storm and high-wind products into inputs.
WINTER_STORM_EVENTS = (
    "blizzard warning",
    "winter storm warning",
    "winter storm watch",
    "ice storm warning",
    "snow squall warning",
    "winter weather advisory",
    "lake effect snow warning",
    "lake effect snow advisory",
)


def parse_active_alerts(alerts_geojson: dict) -> dict:
    """Pure function: NWS /alerts/active FeatureCollection -> winter-storm summary.

    Returns a small dict used to confirm/annotate the gridded forecast:
        {"winter_storm_active": bool, "events": [str, ...]}

    'winter_storm_active' is True when any active feature's 'event' matches a
    known winter-storm product (see WINTER_STORM_EVENTS). Wind-only products
    (e.g. Wind Advisory) do not set it. Safe on empty/missing input.
    """
    features = alerts_geojson.get("features", []) or []
    events: list[str] = []
    for feat in features:
        props = feat.get("properties", {}) or {}
        event = props.get("event")
        if event:
            events.append(event)

    winter_storm_active = any(
        ev.strip().lower() in WINTER_STORM_EVENTS for ev in events
    )
    return {"winter_storm_active": winter_storm_active, "events": events}


# ------------------------------------------------------------------ pure parser

def parse_storm_inputs(grid_props: dict, tz_offset_hours: int = -5) -> dict:
    """Pure function: forecast grid properties -> storm-generator inputs.

    grid_props is the 'properties' object from forecastGridData, containing
    'snowfallAmount' with {'uom': ..., 'values': [{'validTime', 'value'}, ...]}.

    Returns {'snow_inches', 'start_hour', 'duration_hours'} covering the next
    contiguous run of snowfall. tz_offset_hours converts the UTC forecast time
    to local clock hour (Boston is UTC-5 EST / UTC-4 EDT; default EST).
    """
    snow = grid_props.get("snowfallAmount", {}) or {}
    uom = snow.get("uom", "")
    values = snow.get("values", []) or []

    # NWS snowfall is reported in mm (wmoUnit:mm). Convert each positive entry.
    to_inches = (lambda v: v / MM_PER_INCH) if "mm" in uom.lower() else (lambda v: v)

    # Build (start, hours, inches) for every entry with snow > 0.
    snowy: list[tuple[datetime, float, float]] = []
    for entry in values:
        raw = entry.get("value")
        if raw is None or raw <= 0:
            continue
        start, hours = _parse_valid_time(entry.get("validTime", ""))
        snowy.append((start, hours, to_inches(raw)))

    if not snowy:
        return {"snow_inches": 0.0, "start_hour": 0, "duration_hours": 0}

    snowy.sort(key=lambda t: t[0])

    total_inches = round(sum(s[2] for s in snowy), 1)
    first_start = snowy[0][0]
    # Storm span: from the first snowy period's start to the end of the last.
    last_end = snowy[-1][0] + timedelta(hours=snowy[-1][1])
    duration_hours = int(round((last_end - first_start).total_seconds() / 3600.0))

    local_start = first_start + timedelta(hours=tz_offset_hours)
    start_hour = local_start.hour

    return {
        "snow_inches": total_inches,
        "start_hour": start_hour,
        "duration_hours": duration_hours,
    }


# ------------------------------------------------------------------ fetch

def _fetch_grid_props(lat: float, lon: float) -> dict:
    p = httpx.get(f"{NWS}/points/{lat},{lon}", headers=_nws_headers(), timeout=TIMEOUT)
    p.raise_for_status()
    grid_url = p.json()["properties"]["forecastGridData"]
    g = httpx.get(grid_url, headers=_nws_headers(), timeout=TIMEOUT)
    g.raise_for_status()
    return g.json()["properties"]


def _fetch_active_alerts(lat: float, lon: float) -> dict:
    """Fetch /alerts/active for the point. Confirmatory only; never required."""
    a = httpx.get(
        f"{NWS}/alerts/active",
        params={"point": f"{lat},{lon}"},
        headers=_nws_headers(),
        timeout=TIMEOUT,
    )
    a.raise_for_status()
    return parse_active_alerts(a.json())


def _save_snapshot(inputs: dict, fetched_at: str) -> None:
    try:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        NWS_SNAPSHOT.write_text(
            json.dumps({"inputs": inputs, "fetched_at": fetched_at}, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        log.warning("nws snapshot write failed: %s", e.__class__.__name__)


def _load_snapshot() -> tuple[dict, str] | None:
    if not NWS_SNAPSHOT.exists():
        return None
    try:
        obj = json.loads(NWS_SNAPSHOT.read_text(encoding="utf-8"))
        return obj["inputs"], obj["fetched_at"]
    except (OSError, ValueError, KeyError):
        return None


def nws_storm_inputs(lat: float = LONGWOOD_LAT, lon: float = LONGWOOD_LON) -> tuple[dict, str]:
    """Live NWS storm inputs for the study area.

    Returns (inputs, fetched_at) where inputs is:
        {"snow_inches": float, "start_hour": int, "duration_hours": int,
         "stale_since": <iso8601> | None}

    On any network/parse failure, falls back to the last snapshot and sets
    stale_since. If there is no snapshot, returns a zero-snow forecast with
    stale_since = now. Never raises.
    """
    try:
        props = _fetch_grid_props(lat, lon)
        inputs = parse_storm_inputs(props)
        fetched_at = datetime.now(timezone.utc).isoformat()
        inputs["stale_since"] = None
        # Active alerts are confirmatory (Requirement 8.3); never fatal.
        try:
            alerts = _fetch_active_alerts(lat, lon)
            inputs["winter_storm_active"] = alerts["winter_storm_active"]
        except (httpx.HTTPError, ValueError, KeyError) as e:
            log.warning("nws alerts failed (%s); forecast kept without confirmation",
                        e.__class__.__name__)
            inputs["winter_storm_active"] = None
        log.info("nws forecast ok: snow_inches=%s start_hour=%s duration_hours=%s "
                 "winter_storm_active=%s",
                 inputs["snow_inches"], inputs["start_hour"], inputs["duration_hours"],
                 inputs["winter_storm_active"])
        _save_snapshot(inputs, fetched_at)
        return inputs, fetched_at
    except (httpx.HTTPError, ValueError, KeyError) as e:
        log.warning("nws forecast failed (%s); using last snapshot",
                    e.__class__.__name__)
        snap = _load_snapshot()
        if snap is not None:
            inputs, fetched_at = snap
            inputs["stale_since"] = fetched_at
            return inputs, fetched_at
        now = datetime.now(timezone.utc).isoformat()
        return {"snow_inches": 0.0, "start_hour": 0, "duration_hours": 0,
                "stale_since": now}, now


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
    inputs, fetched_at = nws_storm_inputs()
    print(f"fetched_at: {fetched_at}")
    print(f"snow_inches: {inputs['snow_inches']}")
    print(f"start_hour: {inputs['start_hour']}")
    print(f"duration_hours: {inputs['duration_hours']}")
    print(f"stale_since: {inputs['stale_since']}")


if __name__ == "__main__":
    main()
