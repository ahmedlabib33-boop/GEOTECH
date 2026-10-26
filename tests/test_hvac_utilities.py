"""Tests for the HVAC and underground-networks study modules."""
from backend.schemas import (Climate, SoilProfile, SoilLayer, Terrain, Hydrology)
from backend.engineering.hvac import build_hvac, climate_zone
from backend.engineering.utilities import build_underground


def _clay_profile():
    layers = [SoilLayer(depth_label="0-5cm", top_cm=0, bottom_cm=5, clay_pct=55,
                        sand_pct=10, silt_pct=35, ph=5.2, usda_texture="Clay",
                        uscs_group="CH")]
    return SoilProfile(layers=layers, dominant_usda_texture="Clay", dominant_uscs_group="CH")


def _sand_profile():
    layers = [SoilLayer(depth_label="0-5cm", top_cm=0, bottom_cm=5, clay_pct=5,
                        sand_pct=90, silt_pct=5, ph=7.0, usda_texture="Sand",
                        uscs_group="SP")]
    return SoilProfile(layers=layers, dominant_usda_texture="Sand", dominant_uscs_group="SP")


# ---- HVAC ----
def test_climate_zone_hot_vs_cold():
    assert "hot" in climate_zone(100, 2000, "Arid").lower()
    assert "cold" in climate_zone(4500, 50, "Moderate").lower()


def test_hvac_none_without_climate():
    assert build_hvac(Climate(), None, None) is None


def test_hvac_loads_scale_with_area():
    cl = Climate(hdd18=2500, cdd18=300, heating_design_temp_c=-5, cooling_design_temp_c=30,
                 wetness_class="Moderate")
    small = build_hvac(cl, 100, "office")
    big = build_hvac(cl, 1000, "office")
    assert small.peak_heating_kw and big.peak_heating_kw
    assert big.peak_heating_kw > small.peak_heating_kw
    assert big.cooling_tons and big.cooling_tons > 0
    assert big.annual_heating_kwh and big.annual_heating_kwh > 0


def test_hvac_without_area_has_zone_but_no_loads():
    cl = Climate(hdd18=2500, cdd18=300, heating_design_temp_c=-5, cooling_design_temp_c=30)
    h = build_hvac(cl, None, None)
    assert h.climate_zone and h.peak_heating_kw is None


# ---- Underground ----
def test_underground_clay_low_infiltration_and_corrosive():
    u = build_underground(_clay_profile(), Climate(frost_depth_m=0.0, annual_precip_mm=900,
                          wetness_class="Moderate"), Hydrology(), Terrain(slope_deg=0.5),
                          gw_depth_m=1.2)
    assert u.infiltration_class in ("Low", "Very low")
    assert "not recommended" in (u.soakaway_feasibility or "")
    assert u.soil_corrosivity in ("Moderate", "High")   # low pH clay
    assert u.dewatering and "required" in u.dewatering.lower()  # shallow GW
    assert u.min_burial_depth_m >= 0.75


def test_underground_sand_high_infiltration():
    u = build_underground(_sand_profile(), Climate(frost_depth_m=0.6, annual_precip_mm=600,
                          wetness_class="Semi-arid"), Hydrology(), Terrain(slope_deg=3), None)
    assert u.infiltration_class == "High"
    assert "feasible" in (u.soakaway_feasibility or "")
    # frost 0.6 m -> burial >= 0.9 m
    assert u.min_burial_depth_m >= 0.9


def test_underground_unavailable_soil():
    u = build_underground(SoilProfile(), Climate(annual_precip_mm=800), Hydrology(),
                          Terrain(), None)
    assert u.infiltration_class is None
    assert any("unavailable" in n for n in u.notes)
