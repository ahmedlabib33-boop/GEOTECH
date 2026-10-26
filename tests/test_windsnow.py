"""Tests for the wind & snow load study (engineering) and its ERA5 service glue."""
from backend.engineering.windsnow import (build_windsnow, gumbel_return_level,
                                          AIR_DENSITY)
from backend.services.windsnow import _annual_max, _dominant_direction


# ---- Gumbel ----
def test_gumbel_extrapolates_above_mean():
    maxima = [28, 31, 26, 33, 29, 35, 30, 27, 32, 34]
    v50 = gumbel_return_level(maxima, 50)
    assert v50 > max(maxima)          # 50-yr level exceeds a 10-yr observed max
    v10 = gumbel_return_level(maxima, 10)
    assert v50 > v10 > sum(maxima) / len(maxima)


def test_gumbel_too_few_years_returns_max():
    assert gumbel_return_level([30, 40], 50) == 40
    assert gumbel_return_level([], 50) is None


# ---- Wind ----
def test_wind_pressure_scales_with_gust():
    calm = build_windsnow(wind_annual_max_gust_ms=[18, 19, 20, 18, 21], snow_annual_max_depth_m=[])
    storm = build_windsnow(wind_annual_max_gust_ms=[38, 42, 40, 44, 39], snow_annual_max_depth_m=[])
    assert storm.basic_velocity_pressure_kpa > calm.basic_velocity_pressure_kpa
    # q = 0.5 * rho * V^2 — check the physics for the storm design gust
    v = storm.design_gust_ms
    assert abs(storm.basic_velocity_pressure_kpa - 0.5 * AIR_DENSITY * v ** 2 / 1000.0) < 0.02
    assert storm.indicative_wall_pressure_kpa > storm.basic_velocity_pressure_kpa
    assert "high" in storm.wind_class.lower()
    assert storm.design_gust_ms >= max([38, 42, 40, 44, 39])  # never below observed max


# ---- Snow ----
def test_snow_free_site_has_zero_load():
    s = build_windsnow(wind_annual_max_gust_ms=[25] * 5, snow_annual_max_depth_m=[0.0] * 5)
    assert s.snow_zone == "Negligible"
    assert s.ground_snow_load_kpa == 0.0
    assert s.roof_snow_load_kpa == 0.0


def test_snowy_site_has_load_and_roof_below_ground():
    s = build_windsnow(wind_annual_max_gust_ms=[25] * 8,
                       snow_annual_max_depth_m=[0.6, 0.9, 0.7, 1.1, 0.8, 1.0, 0.75, 0.95])
    assert s.ground_snow_load_kpa and s.ground_snow_load_kpa > 0
    assert s.roof_snow_load_kpa < s.ground_snow_load_kpa      # flat-roof shape factor 0.8
    assert s.snow_zone in ("Light", "Moderate", "Heavy", "Very heavy")
    assert s.design_snow_depth_m >= max([0.6, 0.9, 0.7, 1.1, 0.8, 1.0, 0.75, 0.95])


def test_no_data_returns_none():
    assert build_windsnow(wind_annual_max_gust_ms=[], snow_annual_max_depth_m=[]) is None
    assert build_windsnow() is None


# ---- Service helpers ----
def test_annual_max_groups_by_year():
    times = ["2020-01-01", "2020-06-01", "2021-03-01", "2021-09-01"]
    vals = [10, 25, 30, 12]
    assert _annual_max(times, vals) == [25, 30]       # per-year maxima, year-sorted


def test_annual_max_skips_nulls():
    assert _annual_max(["2020-01-01", "2020-02-01"], [None, 5]) == [5]


def test_dominant_direction_modal_sector():
    # mostly westerly
    assert _dominant_direction([270, 268, 272, 90, 271]) == "W"
    assert _dominant_direction([None, None]) is None
