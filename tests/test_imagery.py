"""Tests for the keyless Sentinel-2 imagery-recency parser."""
from datetime import date

from backend.services.imagery import _parse, CLEAR_CLOUD_PCT


def _prod(day, cloud):
    attrs = [] if cloud is None else [{"Name": "cloudCover", "Value": cloud}]
    return {"ContentDate": {"Start": f"{day}T08:30:00.000Z"}, "Attributes": attrs}


TODAY = date(2026, 10, 28)


def test_picks_latest_pass_and_latest_clear():
    products = [
        _prod("2026-10-26", 98.8),   # newest but cloudy
        _prod("2026-10-24", 3.8),    # newest usable
        _prod("2026-10-19", 2.1),
    ]
    im = _parse(products, TODAY)
    assert im.latest_pass_date == "2026-10-26"
    assert im.latest_pass_cloud_pct == 98.8
    assert im.latest_pass_days_ago == 2
    assert im.latest_clear_date == "2026-10-24"       # first below the cloud threshold
    assert im.latest_clear_cloud_pct < CLEAR_CLOUD_PCT
    assert im.latest_clear_days_ago == 4
    assert im.passes_in_window == 3


def test_unordered_input_is_sorted():
    im = _parse([_prod("2026-09-01", 5.0), _prod("2026-10-20", 10.0),
                 _prod("2026-10-01", 7.0)], TODAY)
    assert im.latest_pass_date == "2026-10-20"


def test_all_cloudy_sets_note_and_no_clear():
    im = _parse([_prod("2026-10-20", 80.0), _prod("2026-10-15", 55.0)], TODAY)
    assert im.latest_pass_date == "2026-10-20"
    assert im.latest_clear_date is None
    assert im.note and "cloud" in im.note.lower()


def test_empty_returns_none():
    assert _parse([], TODAY) is None


def test_missing_cloud_attribute_is_tolerated():
    im = _parse([_prod("2026-10-20", None)], TODAY)
    assert im.latest_pass_date == "2026-10-20"
    assert im.latest_pass_cloud_pct is None
    assert im.latest_clear_date is None   # unknown cloud can't count as 'clear'
