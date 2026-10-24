"""Tests for the 311 snow validation layer (task 9.1). No live calls.

Covers Requirement 14.1 (snow complaints clustered by street)."""
from __future__ import annotations

from src.validation.snow311 import (
    summarize_by_street,
    _is_snow_case,
    _street_from_location,
    overlap_with_slowed_streets,
)

# A mix: snow cases in-bbox, a non-snow case, and one outside the bbox.
RECORDS = [
    {"case_title": "Snow Plowing", "street_name": "Huntington Ave",
     "latitude": 42.337, "longitude": -71.102},
    {"case_title": "Snow Plowing", "street_name": "Huntington Ave",
     "latitude": 42.338, "longitude": -71.101},
    {"case_title": "Snow/Ice Removal", "street_name": "Longwood Ave",
     "latitude": 42.339, "longitude": -71.106},
    {"case_title": "Pothole Repair", "street_name": "Huntington Ave",
     "latitude": 42.337, "longitude": -71.102},
    {"case_title": "Snow Plowing", "street_name": "Alewife Brook Pkwy",
     "latitude": 42.395, "longitude": -71.140},
]


def test_counts_snow_cases_by_street_in_bbox():
    out = summarize_by_street(RECORDS)
    as_dict = {r["street"]: r["count"] for r in out}
    assert as_dict.get("Huntington Ave") == 2
    assert as_dict.get("Longwood Ave") == 1


def test_excludes_non_snow_cases():
    out = summarize_by_street(RECORDS)
    # The pothole on Huntington must not inflate its count beyond the 2 snow ones.
    assert {r["street"]: r["count"] for r in out}["Huntington Ave"] == 2


def test_excludes_out_of_bbox():
    out = summarize_by_street(RECORDS)
    assert "Alewife Brook Pkwy" not in {r["street"] for r in out}


def test_sorted_descending():
    out = summarize_by_street(RECORDS)
    counts = [r["count"] for r in out]
    assert counts == sorted(counts, reverse=True)


def test_is_snow_case():
    assert _is_snow_case("Snow Plowing")
    assert _is_snow_case("Snow/Ice Removal")
    assert not _is_snow_case("Pothole Repair")


def test_street_from_location():
    assert _street_from_location("123 Huntington Ave, Boston") == "Huntington Ave"
    assert _street_from_location(None) is None


# --- overlap metric (Requirement 14.1) ------------------------------------

def test_overlap_reports_shared_streets_case_insensitively():
    complaints = summarize_by_street(RECORDS)  # Huntington Ave (2), Longwood Ave (1)
    # Generator slows these most; note casing differs from the 311 labels.
    slowed = ["HUNTINGTON AVENUE", "Tremont Street", "longwood ave"]
    report = overlap_with_slowed_streets(complaints, slowed)
    assert "Huntington Ave" in report["overlap"]
    assert "Longwood Ave" in report["overlap"]
    assert report["overlap_count"] == 2


def test_overlap_pct_is_jaccard_of_top_sets():
    # 2 shared, union = {Huntington, Longwood, Tremont} = 3 -> 66.7%
    complaints = summarize_by_street(RECORDS)
    slowed = ["Huntington Ave", "Longwood Ave", "Tremont Street"]
    report = overlap_with_slowed_streets(complaints, slowed)
    assert report["overlap_pct"] == 66.7


def test_overlap_empty_when_no_shared_streets():
    complaints = summarize_by_street(RECORDS)
    report = overlap_with_slowed_streets(complaints, ["Some Other Road"])
    assert report["overlap"] == []
    assert report["overlap_count"] == 0
    assert report["overlap_pct"] == 0.0


def test_overlap_handles_empty_inputs():
    report = overlap_with_slowed_streets([], [])
    assert report["overlap"] == []
    assert report["overlap_pct"] == 0.0


def test_sample_fixture_produces_overlap_offline():
    """End-to-end validation metric (Req 14.1) runs offline off the sample
    fixture: the sampled snow complaints overlap the bbox priority routes."""
    from src.validation.snow311 import load_sample_records
    from config.params import PRIORITY_ROUTES

    streets = summarize_by_street(load_sample_records())
    assert streets, "sample fixture should yield snow complaints in the bbox"
    report = overlap_with_slowed_streets(streets, PRIORITY_ROUTES)
    # Sample has Huntington/Longwood/Tremont/Ruggles/Hemenway complaints, all of
    # which are PRIORITY_ROUTES, so there must be a real overlap.
    assert report["overlap_count"] >= 1
    assert report["overlap_pct"] > 0.0
