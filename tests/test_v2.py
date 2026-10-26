"""Tests for the v2 engineering additions (no network)."""
from backend.services.climate import frost_depth_from_fdd, wetness
from backend.engineering.classification import seismic_site_class, stiffness_for
from backend.engineering.bearing import elastic_settlement_mm, settlement_sensitivity


def test_frost_depth_monotonic():
    assert frost_depth_from_fdd(0) == 0.0
    assert frost_depth_from_fdd(100) > 0
    assert frost_depth_from_fdd(1000) > frost_depth_from_fdd(100)
    assert frost_depth_from_fdd(10_000_000) <= 3.0  # capped


def test_wetness_buckets():
    assert wetness(100) == "Arid"
    assert wetness(800) == "Moderate"
    assert wetness(3000) == "Very wet"
    assert wetness(None) is None


def test_site_class():
    assert seismic_site_class(800).startswith("B")
    assert seismic_site_class(400).startswith("C")
    assert seismic_site_class(200).startswith("D")
    assert seismic_site_class(120).startswith("E")


def test_stiffness_lookup():
    es, vs = stiffness_for("Clay")
    assert es > 0 and vs > 0
    es2, vs2 = stiffness_for("Sand")
    assert vs2 > vs  # sand stiffer than clay


def test_settlement_increases_with_load():
    low = elastic_settlement_mm(100, 2.0, 30)
    high = elastic_settlement_mm(300, 2.0, 30)
    assert high > low >= 0
    assert "tolerance" in settlement_sensitivity(10) or settlement_sensitivity(10)
