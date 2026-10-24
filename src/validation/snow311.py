"""311 snow/plow complaints as a validation layer. Owner: A. (optional, stretch)

Task 9.1: Pull snow/plow-related 311 requests in the study-area bbox for a past
Boston blizzard date from Analyze Boston, so they can be compared with the
streets the storm generator slows most. (Requirement 14.1)

This is a VALIDATION layer only. It never feeds the simulator or routing; it is
display/comparison data. The simulator must not import this module.

Analyze Boston conventions (steering/data-sources.md):
  - CKAN SQL endpoint: GET /api/3/action/datastore_search_sql?sql=...
  - 311 requests resource; filter by snow/plow-related case types and dates.
    The exact case_title / type strings vary, so match them case-insensitively.

Adapter discipline: return (result, fetched_at); never raise to callers; fall
back to the last snapshot with stale_since; log counts only (never addresses).
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx

from config.params import BBOX, PRIORITY_ROUTES

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = PROJECT_ROOT / "data" / "snapshots"
SNOW311_SNAPSHOT = SNAPSHOT_DIR / "snow311_latest.json"
# Small, clearly-marked sample for offline/demo use (see the file's _note).
SAMPLE_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "snow311_sample.json"

CKAN = "https://data.boston.gov/api/3/action/datastore_search_sql"
TIMEOUT = 10.0

# Boston 311 "service requests" datastore resource id (public).
RESOURCE_ID = "dff4d804-5031-443a-8409-8344efd0e5c8"

# Snow/plow-related case titles are matched case-insensitively against these
# fragments; the city uses several variants ("Snow Plowing", "Snow/Ice ...").
SNOW_KEYWORDS = ("snow", "plow", "ice")

log = logging.getLogger("validation.snow311")


# ------------------------------------------------------------------ pure parsing

def _is_snow_case(title: str) -> bool:
    low = (title or "").lower()
    return any(k in low for k in SNOW_KEYWORDS)


def _in_bbox(lat, lon) -> bool:
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return False
    return (BBOX["south"] <= lat <= BBOX["north"]
            and BBOX["west"] <= lon <= BBOX["east"])


def summarize_by_street(records: list[dict]) -> list[dict]:
    """Pure function: 311 records -> snow complaints per street, descending.

    Keeps only snow/plow cases inside the bbox. Returns
    [{"street": name, "count": n}, ...] sorted by count. Street name is read
    from common 311 columns; rows without a usable street are grouped as
    "(unknown)". No addresses or personal fields are retained.
    """
    counts: Counter[str] = Counter()
    for rec in records:
        title = rec.get("case_title") or rec.get("type") or ""
        if not _is_snow_case(title):
            continue
        if not _in_bbox(rec.get("latitude"), rec.get("longitude")):
            continue
        street = (rec.get("street_name") or rec.get("street")
                  or _street_from_location(rec.get("location")) or "(unknown)")
        counts[str(street).strip().title()] += 1
    return [{"street": s, "count": c} for s, c in counts.most_common()]


def _street_from_location(location: str | None) -> str | None:
    """Best-effort street name from a free-text 'location' field."""
    if not location:
        return None
    # Drop a leading house number, keep the rest up to a comma.
    head = location.split(",")[0].strip()
    parts = head.split()
    if parts and parts[0].isdigit():
        parts = parts[1:]
    return " ".join(parts) or None


# ------------------------------------------------------------------ overlap (Req 14.1)

# Street-type suffixes get collapsed to a canonical form so the two data sources
# match ("Huntington Ave" from 311 vs "Huntington Avenue" from OSM edge names).
_SUFFIX_CANON = {
    "ave": "ave", "avenue": "ave",
    "st": "st", "street": "st",
    "rd": "rd", "road": "rd",
    "dr": "dr", "drive": "dr",
    "pkwy": "pkwy", "parkway": "pkwy",
    "blvd": "blvd", "boulevard": "blvd",
    "ln": "ln", "lane": "ln",
    "pl": "pl", "place": "pl",
    "ct": "ct", "court": "ct",
    "sq": "sq", "square": "sq",
    "ter": "ter", "terrace": "ter",
    "hwy": "hwy", "highway": "hwy",
}


def _norm_street(name: str) -> str:
    """Normalize a street name so '311' labels and generator edge names match.

    Lowercases, collapses whitespace, strips punctuation, and canonicalizes the
    trailing street-type suffix ('Avenue' -> 'ave', 'Street' -> 'st', ...).
    """
    cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in (name or ""))
    parts = cleaned.lower().split()
    if parts and parts[-1] in _SUFFIX_CANON:
        parts[-1] = _SUFFIX_CANON[parts[-1]]
    return " ".join(parts)


def overlap_with_slowed_streets(
    complaint_streets: list[dict],
    slowed_streets: list[str],
    top_n: int = 10,
) -> dict:
    """Compare 311 snow-complaint clusters with the streets the storm generator
    slows most, and report the overlap. (Requirement 14.1)

    This is the validation metric. It is pure and takes the generator's slowed
    streets as input (the caller reads them off the simulated edges by name), so
    this module never imports the simulator and never feeds routing.

    Args:
        complaint_streets: output of ``summarize_by_street`` (descending by count).
        slowed_streets: street names the generator slows most, most-slowed first.
        top_n: how many streets from each side to compare.

    Returns a dict with the two top lists, the overlapping street names, and a
    Jaccard-style ``overlap_pct`` (shared / union of the two top-N sets).
    """
    top_complaints = [r["street"] for r in complaint_streets[:top_n]]
    top_slowed = list(slowed_streets[:top_n])

    comp_norm = {_norm_street(s): s for s in top_complaints}
    slow_norm = {_norm_street(s): s for s in top_slowed}

    shared_keys = [k for k in comp_norm if k in slow_norm]
    overlap = [comp_norm[k] for k in shared_keys]
    union = set(comp_norm) | set(slow_norm)
    overlap_pct = round(100.0 * len(shared_keys) / len(union), 1) if union else 0.0

    return {
        "top_complaint_streets": top_complaints,
        "top_slowed_streets": top_slowed,
        "overlap": overlap,
        "overlap_count": len(overlap),
        "overlap_pct": overlap_pct,
    }


# ------------------------------------------------------------------ fetch

def load_sample_records() -> list[dict]:
    """Load the bundled SAMPLE 311 records (offline/demo). Returns [] if absent.

    This is sample data, not real Analyze Boston output; it exists so the
    validation layer and its overlap metric can be demonstrated without a live
    CKAN call. Feed the result to ``summarize_by_street``.
    """
    try:
        obj = json.loads(SAMPLE_FIXTURE.read_text(encoding="utf-8"))
        return list(obj.get("records", []))
    except (OSError, ValueError):
        return []


def _build_sql(date_start: str, date_end: str, limit: int = 2000) -> str:
    # Pull requests opened in the storm window; filter snow cases + bbox in
    # Python so we don't depend on exact column names in the SQL.
    return (
        f'SELECT * FROM "{RESOURCE_ID}" '
        f"WHERE open_dt >= '{date_start}' AND open_dt < '{date_end}' "
        f"LIMIT {limit}"
    )


def _fetch_records(date_start: str, date_end: str) -> list[dict]:
    r = httpx.get(CKAN, params={"sql": _build_sql(date_start, date_end)},
                  timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["result"]["records"]


def _save_snapshot(streets: list[dict], fetched_at: str, window: tuple[str, str]) -> None:
    try:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        SNOW311_SNAPSHOT.write_text(
            json.dumps({"streets": streets, "fetched_at": fetched_at,
                        "window": window}, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        log.warning("snow311 snapshot write failed: %s", e.__class__.__name__)


def _load_snapshot() -> tuple[list[dict], str] | None:
    if not SNOW311_SNAPSHOT.exists():
        return None
    try:
        obj = json.loads(SNOW311_SNAPSHOT.read_text(encoding="utf-8"))
        return obj["streets"], obj["fetched_at"]
    except (OSError, ValueError, KeyError):
        return None


def snow_complaints_by_street(date_start: str, date_end: str) -> tuple[list[dict], str]:
    """Snow/plow 311 complaints per street in the bbox for a storm window.

    date_start/date_end are ISO dates (e.g. "2022-01-29", "2022-02-01").
    Returns (streets, fetched_at); streets is descending by count.
    On failure, falls back to the last snapshot with stale info. Never raises.
    """
    try:
        records = _fetch_records(date_start, date_end)
        streets = summarize_by_street(records)
        fetched_at = datetime.now(timezone.utc).isoformat()
        log.info("snow311 ok: %d raw records, %d streets with snow complaints",
                 len(records), len(streets))
        _save_snapshot(streets, fetched_at, (date_start, date_end))
        return streets, fetched_at
    except (httpx.HTTPError, ValueError, KeyError) as e:
        log.warning("snow311 fetch failed (%s); using last snapshot",
                    e.__class__.__name__)
        snap = _load_snapshot()
        if snap is not None:
            return snap
        return [], datetime.now(timezone.utc).isoformat()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
    # A past Boston blizzard: the late-Jan 2022 nor'easter.
    streets, fetched_at = snow_complaints_by_street("2022-01-29", "2022-02-02")
    if not streets:
        # Offline/demo: fall back to the bundled sample so the layer still
        # shows something (clearly labeled as sample data).
        print("(no live/snapshot data; using bundled SAMPLE fixture)")
        streets = summarize_by_street(load_sample_records())
    print(f"fetched_at: {fetched_at}")
    print(f"streets with snow/plow 311 complaints in bbox: {len(streets)}")
    for row in streets[:15]:
        print(f"  {row['count']:4d}  {row['street']}")

    # Validation (Req 14.1): overlap with the streets the generator slows most.
    # The caller normally reads these off the simulated edges; here we use the
    # bbox priority routes as a stand-in so the layer runs without the simulator.
    report = overlap_with_slowed_streets(streets, PRIORITY_ROUTES)
    print(f"\noverlap with most-slowed streets: {report['overlap_count']} "
          f"({report['overlap_pct']}% of the combined top streets)")
    for s in report["overlap"]:
        print(f"  shared: {s}")


if __name__ == "__main__":
    main()
