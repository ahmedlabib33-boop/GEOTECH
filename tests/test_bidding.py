"""Tests for the overseas-bidding layer: country context, logistics helpers,
construction workability and the bid risk register."""
from backend.schemas import (Climate, GeotechParameters, HazardRating, Location,
                             SiteLogistics)
from backend.engineering.country import build_country_context, utm_zone
from backend.engineering.construction_climate import build_construction_climate
from backend.engineering.bid import build_bid_risk
from backend.services.logistics import _classify, _rating


# ---- Country / regulatory context ----
def test_utm_zone_and_hemisphere():
    # London ~ zone 30N, EPSG:32630
    z, epsg = utm_zone(51.5, -0.1)
    assert z == "30N" and epsg == "EPSG:32630"
    # Sydney ~ zone 56S
    z2, epsg2 = utm_zone(-33.9, 151.2)
    assert z2.endswith("S") and epsg2.startswith("EPSG:327")


def test_country_context_eurocode_and_currency():
    ctx = build_country_context(Location(lat=48.85, lon=2.35, country="France", country_code="FR"))
    assert "Eurocode" in ctx.structural_code
    assert ctx.seismic_code.startswith("EN 1998")
    assert ctx.currency.startswith("EUR")
    assert ctx.hemisphere == "Northern"
    assert ctx.measurement_system.startswith("Metric")


def test_country_context_us_is_asce_and_imperial():
    ctx = build_country_context(Location(lat=40.7, lon=-74.0, country="United States", country_code="US"))
    assert "ASCE" in ctx.structural_code
    assert "customary" in ctx.measurement_system
    assert any("Eurocode 8 format" in n for n in ctx.notes)  # spectrum-mapping note


def test_country_context_unknown_code_warns():
    ctx = build_country_context(Location(lat=0.0, lon=0.0, country="Nowhere", country_code="ZZ"))
    assert ctx.structural_code is None
    assert any("governing structural" in n for n in ctx.notes)


# ---- Logistics helpers ----
def test_logistics_classify():
    assert _classify({"harbour": "yes"}) == "seaport"
    assert _classify({"aeroway": "aerodrome"}) == "airport"
    assert _classify({"highway": "trunk"}) == "major_road"
    assert _classify({"place": "town"}) == "urban_centre"
    assert _classify({"landuse": "quarry"}) == "quarry"
    assert _classify({"amenity": "cafe"}) is None


def test_logistics_rating_easy_vs_remote():
    easy, _ = _rating(40, 3, 10)
    remote, note = _rating(None, 80, None)
    assert easy == "Easy"
    assert remote == "Remote"
    assert "no seaport" in note


# ---- Construction workability ----
def test_construction_climate_rating_scales_with_bad_weather():
    mild = build_construction_climate(Climate(annual_precip_mm=600, heavy_rain_days=15,
                                              extreme_heat_days=2, frost_days=5))
    harsh = build_construction_climate(Climate(annual_precip_mm=2500, heavy_rain_days=120,
                                               extreme_heat_days=60, frost_days=40,
                                               wettest_month="July", driest_month="January"))
    assert mild.workable_days_per_year > harsh.workable_days_per_year
    assert harsh.workable_days_per_year >= 120          # bounded floor
    assert any("earthworks" in n or "rain" in n for n in harsh.notes)


def test_construction_climate_none_without_data():
    assert build_construction_climate(Climate()) is None


# ---- Bid risk register ----
def _hazards():
    return [
        HazardRating(name="Flooding / inundation", level="Moderate", score=0.45, rationale="x"),
        HazardRating(name="Slope instability / landslide", level="Low", score=0.1, rationale="x"),
        HazardRating(name="Seismicity", level="High", score=0.7, rationale="x"),
        HazardRating(name="Expansive / shrink-swell soil", level="Very High", score=0.85, rationale="x"),
        HazardRating(name="Liquefaction potential", level="Insufficient data", score=0.0, rationale="n/a"),
    ]


def test_bid_risk_index_and_drivers():
    params = GeotechParameters(recommended_foundation="Deep (piled) foundations or significant ground improvement",
                               data_basis="satellite-model", allowable_bearing_kpa=60, settlement_mm=70)
    logi = SiteLogistics(mobilization_rating="Remote", access_note="no seaport within 300 km")
    cc = build_construction_climate(Climate(annual_precip_mm=2500, heavy_rain_days=120,
                                            extreme_heat_days=10, frost_days=0))
    ctx = build_country_context(Location(lat=10.0, lon=20.0, country="Nowhere", country_code="ZZ"))
    reg = build_bid_risk(_hazards(), params, logi, cc, ctx)
    assert reg.index is not None and 0 <= reg.index <= 100
    assert reg.overall_rating in ("Low", "Moderate", "High", "Very High")
    cats = {it.category for it in reg.items}
    assert {"Ground & foundations", "Seismic", "Flooding", "Logistics & mobilization"} <= cats
    # a high-score line carries a contingency driver
    ground = next(it for it in reg.items if it.category == "Ground & foundations")
    assert ground.contingency_driver and ground.score >= 0.75
    assert "bid-risk" in reg.summary.lower()


def test_bid_risk_handles_missing_soil():
    params = GeotechParameters(data_basis="unavailable")
    reg = build_bid_risk(_hazards(), params, None, None, None)
    ground = next(it for it in reg.items if it.category == "Ground & foundations")
    assert ground.level == "Insufficient data"
    # index still computes from the remaining scored lines
    assert reg.index is not None
