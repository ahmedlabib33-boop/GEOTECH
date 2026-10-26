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


def test_vegetation_reduces_landslide():
    from backend.schemas import Terrain, SoilProfile, Climate, Vegetation
    from backend.engineering.hazards import landslide_hazard
    terr = Terrain(slope_deg=25.0)
    soil = SoilProfile()
    clim = Climate(annual_precip_mm=1500)
    bare = landslide_hazard(terr, soil, clim, Vegetation(ndvi=0.05))
    green = landslide_hazard(terr, soil, clim, Vegetation(ndvi=0.85))
    assert green.score < bare.score  # vegetation stabilises slopes
