"""Tests for the 311 snow validation layer (task 9.1). No live calls.

Covers Requirement 14.1 (snow complaints clustered by street)."""
from __future__ import annotations

from src.validation.snow311 import summarize_by_street, _is_snow_case, _street_from_location

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
