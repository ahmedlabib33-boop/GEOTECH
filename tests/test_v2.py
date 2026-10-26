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


def test_ndvi_cover_classes():
    from backend.services.vegetation import cover_class
    assert cover_class(0.05)[0].startswith("Barren")
    assert cover_class(0.2)[0].startswith("Sparse")
    assert cover_class(0.45)[0].startswith("Moderate")
    assert cover_class(0.8)[0].startswith("Dense")


def test_flood_hazard_higher_near_water_lowland():
    from backend.schemas import Terrain, Climate, Hydrology
    from backend.engineering.hazards import flood_hazard
    low = flood_hazard(Terrain(elevation_m=3, slope_deg=0.5),
                       Climate(annual_precip_mm=1800),
                       Hydrology(nearest_water_m=50, nearest_water_type="river",
                                 river_discharge_m3s=800))
    high_ground = flood_hazard(Terrain(elevation_m=800, slope_deg=18),
                               Climate(annual_precip_mm=300),
                               Hydrology(nearest_water_m=4800, nearest_water_type="stream"))
    assert low.score > high_ground.score
    assert low.name == "Flooding / inundation"


def test_full_bearing_groundwater_reduces():
    from backend.engineering.bearing import allowable_bearing_full
    _, dry = allowable_bearing_full(0, 32, 19, 2.0, 2.0, 1.5, gw_depth_m=None)
    _, wet = allowable_bearing_full(0, 32, 19, 2.0, 2.0, 1.5, gw_depth_m=0.5)
    assert wet < dry        # water table at surface lowers bearing


def test_full_bearing_shape_effect():
    from backend.engineering.bearing import allowable_bearing_full
    _, square = allowable_bearing_full(0, 32, 19, 2.0, 2.0, 1.5)
    _, strip = allowable_bearing_full(0, 32, 19, 2.0, 100.0, 1.5)
    assert abs(square - strip) > 1   # shape factors change the result


def test_influence_weighted_uses_zone():
    from backend.schemas import SoilProfile, SoilLayer, Terrain, Climate
    from backend.engineering.parameters import build_parameters
    # Sand near surface, stiff clay deeper; deep footing should feel the clay.
    layers = [
        SoilLayer(depth_label="0-5cm", top_cm=0, bottom_cm=30, usda_texture="Sand",
                  sand_pct=90, silt_pct=5, clay_pct=5),
        SoilLayer(depth_label="30-200cm", top_cm=30, bottom_cm=200, usda_texture="Clay",
                  sand_pct=10, silt_pct=20, clay_pct=70),
    ]
    sp = SoilProfile(layers=layers, dominant_usda_texture="Sand")
    shallow = build_parameters(sp, Terrain(slope_deg=0), Climate(), 1.0, 0.0)
    deep = build_parameters(sp, Terrain(slope_deg=0), Climate(), 1.0, 1.5)
    # Shallow zone (0-1.5 m) includes the sand; deep zone (1.5-3 m) is all clay.
    assert deep.cohesion_kpa > shallow.cohesion_kpa


def test_borehole_override_sand():
    from backend.schemas import Borehole, BoreholeLayer
    from backend.engineering.borehole import build_parameters_from_borehole, has_usable_data
    bh = Borehole(layers=[
        BoreholeLayer(top_m=0, bottom_m=1.5, description="loose SAND", uscs="SP", spt_n=8),
        BoreholeLayer(top_m=1.5, bottom_m=6, description="dense SAND", uscs="SP", spt_n=35)],
        groundwater_depth_m=4.0)
    assert has_usable_data(bh)
    p = build_parameters_from_borehole(bh, 2.0, 1.5)
    assert p.data_basis == "borehole"
    assert p.friction_angle_deg > 28           # dense sand founding layer
    assert p.allowable_bearing_kpa > 0
    assert p.bearing_curve


def test_borehole_override_clay_is_weaker():
    from backend.schemas import Borehole, BoreholeLayer
    from backend.engineering.borehole import build_parameters_from_borehole
    soft = build_parameters_from_borehole(
        Borehole(layers=[BoreholeLayer(top_m=0, bottom_m=6, description="soft CLAY",
                                       uscs="CL", spt_n=3)]), 2.0, 1.5)
    stiff = build_parameters_from_borehole(
        Borehole(layers=[BoreholeLayer(top_m=0, bottom_m=6, description="stiff CLAY",
                                       uscs="CL", spt_n=20)]), 2.0, 1.5)
    assert soft.allowable_bearing_kpa < stiff.allowable_bearing_kpa
    assert soft.cohesion_kpa < stiff.cohesion_kpa


def test_soil_confidence_from_spread():
    from backend.schemas import SoilProfile, SoilLayer
    from backend.services.soil import _assign_confidence
    tight = SoilProfile(layers=[SoilLayer(depth_label="0-5cm", top_cm=0, bottom_cm=5,
                                          clay_low_pct=20, clay_high_pct=28)])
    wide = SoilProfile(layers=[SoilLayer(depth_label="0-5cm", top_cm=0, bottom_cm=5,
                                         clay_low_pct=10, clay_high_pct=55)])
    _assign_confidence(tight)
    _assign_confidence(wide)
    assert tight.texture_confidence == "High"
    assert wide.texture_confidence == "Low"


def test_llm_disabled_without_key(monkeypatch):
    import backend.llm as llm
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from backend.schemas import (Assessment, Location, Terrain, SoilProfile,
                                 SeismicContext, GeotechParameters)
    a = Assessment(project_name="x", generated_utc="now",
                   location=Location(lat=0, lon=0), terrain=Terrain(),
                   soil=SoilProfile(), seismic=SeismicContext(search_radius_km=300),
                   parameters=GeotechParameters())
    text, model = llm.generate_commentary(a)
    assert text is None and model is None


def test_vegetation_reduces_landslide():
    from backend.schemas import Terrain, SoilProfile, Climate, Vegetation
    from backend.engineering.hazards import landslide_hazard
    terr = Terrain(slope_deg=25.0)
    soil = SoilProfile()
    clim = Climate(annual_precip_mm=1500)
    bare = landslide_hazard(terr, soil, clim, Vegetation(ndvi=0.05))
    green = landslide_hazard(terr, soil, clim, Vegetation(ndvi=0.85))
    assert green.score < bare.score  # vegetation stabilises slopes
