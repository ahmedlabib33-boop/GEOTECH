"""Tests for the seismic design study / EC8 elastic response spectrum."""
from backend.schemas import SeismicContext
from backend.engineering.seismic_design import (build_seismic_design, ec8_ground_type,
                                                ec8_spectrum_value)


def _seismic(pga=0.18, mag=6.4):
    return SeismicContext(search_radius_km=300.0, event_count=12, max_magnitude=mag,
                          nearest_significant_km=40.0, estimated_pga_g=pga,
                          hazard_level="High", source="USGS Earthquake Catalog (FDSN)")


# ---- Ground type mapping ----
def test_ground_type_thresholds():
    assert ec8_ground_type(900) == "A"
    assert ec8_ground_type(500) == "B"
    assert ec8_ground_type(250) == "C"
    assert ec8_ground_type(120) == "D"
    assert ec8_ground_type(None) is None


# ---- Spectrum shape / physics ----
def test_user_pga_builds_spectrum_with_correct_plateau():
    sd = build_seismic_design(_seismic(), vs30_proxy=300, user_pga_g=0.25)
    assert sd.design_ground_accel_g == 0.25
    assert sd.ground_type == "C"
    # plateau = ag * S * 2.5 (stored rounded to 3 dp)
    assert abs(sd.plateau_sa_g - 0.25 * sd.soil_factor_s * 2.5) < 1e-3
    # Se(0) = ag * S (first spectrum point at T=0)
    first = sd.spectrum[0]
    assert first.period_s == 0.0
    assert abs(first.sa_g - 0.25 * sd.soil_factor_s) < 1e-3
    # peak ordinate equals the plateau; nothing exceeds it
    assert abs(max(p.sa_g for p in sd.spectrum) - sd.plateau_sa_g) < 1e-2
    # spectrum decays in the TD..4s branch
    long = [p.sa_g for p in sd.spectrum if p.period_s >= sd.t_d_s]
    assert long == sorted(long, reverse=True)
    assert "User-supplied" in sd.ag_basis


def test_plateau_holds_between_tb_and_tc():
    sd = build_seismic_design(_seismic(), vs30_proxy=600, user_pga_g=0.2)
    mid = (sd.t_b_s + sd.t_c_s) / 2
    val = ec8_spectrum_value(mid, 0.2, sd.soil_factor_s, sd.t_b_s, sd.t_c_s, sd.t_d_s)
    assert abs(val - sd.plateau_sa_g) < 1e-6


def test_spectrum_type_from_magnitude():
    far = build_seismic_design(_seismic(mag=6.8), vs30_proxy=400, user_pga_g=0.2)
    near = build_seismic_design(_seismic(mag=5.0), vs30_proxy=400, user_pga_g=0.2)
    assert far.spectrum_type == 1
    assert near.spectrum_type == 2


# ---- Real-only anchoring ----
def test_catalogue_screening_anchor_is_flagged():
    sd = build_seismic_design(_seismic(pga=0.15, mag=6.0), vs30_proxy=250, user_pga_g=None)
    assert sd.design_ground_accel_g == 0.15
    assert "Screening PGA" in sd.ag_basis and "NOT a probabilistic" in sd.ag_basis


def test_no_pga_and_no_events_gives_note_not_spectrum():
    quiet = SeismicContext(search_radius_km=300.0, event_count=0, estimated_pga_g=None,
                           source="USGS Earthquake Catalog (FDSN)")
    sd = build_seismic_design(quiet, vs30_proxy=400, user_pga_g=None)
    assert sd is not None
    assert sd.design_ground_accel_g is None
    assert not sd.spectrum
    assert any("No design ground motion" in n for n in sd.notes)


def test_unavailable_seismic_without_pga_returns_none():
    un = SeismicContext(search_radius_km=300.0, source="unavailable")
    assert build_seismic_design(un, vs30_proxy=300, user_pga_g=None) is None
    assert build_seismic_design(None, vs30_proxy=300, user_pga_g=None) is None


def test_missing_vs30_falls_back_to_reference_rock():
    sd = build_seismic_design(_seismic(), vs30_proxy=None, user_pga_g=0.2)
    assert sd.ground_type == "A"
    assert sd.soil_factor_s == 1.0           # no amplification on reference rock
    assert any("reference rock" in n for n in sd.notes)
