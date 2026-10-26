"""Unit tests for the engineering interpretation layer (no network)."""
import math

from backend.engineering.classification import usda_texture, usda_to_uscs, params_for
from backend.engineering.bearing import bearing_factors, allowable_bearing, slope_reduction


def test_texture_endmembers():
    assert usda_texture(95, 3, 2) == "Sand"
    assert usda_texture(20, 20, 60) == "Clay"
    assert usda_texture(10, 85, 5) == "Silt"
    assert usda_texture(40, 40, 20) == "Loam"


def test_texture_handles_missing():
    assert usda_texture(None, 10, 10) is None


def test_uscs_mapping():
    assert usda_to_uscs("Clay") == "CH"
    assert usda_to_uscs("Sand") == "SP"
    assert usda_to_uscs(None) is None


def test_bearing_factors_phi_zero():
    nc, nq, ngamma = bearing_factors(0)
    assert abs(nc - 5.14) < 0.01 and nq == 1.0 and ngamma == 0.0


def test_bearing_factors_phi30_reasonable():
    nc, nq, ngamma = bearing_factors(30)
    # Published Terzaghi/Vesic values at phi=30: Nq~18.4, Nc~30.1
    assert 17 < nq < 20
    assert 28 < nc < 32
    assert ngamma > 0


def test_allowable_increases_with_friction():
    _, low = allowable_bearing(0, 25, 18, 2, 1.5)
    _, high = allowable_bearing(0, 38, 18, 2, 1.5)
    assert high > low > 0


def test_slope_reduction_monotonic():
    assert slope_reduction(0) == 1.0
    assert slope_reduction(8) < 1.0
    assert slope_reduction(35) < slope_reduction(15)


def test_params_for_defaults():
    p = params_for("DoesNotExist")
    assert "phi" in p and "bearing" in p
