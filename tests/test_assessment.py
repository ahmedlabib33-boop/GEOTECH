"""End-to-end tests of the assessment orchestrator (offline fixtures)."""
import asyncio

from backend.schemas import AssessRequest, Assessment
from backend.assess import run_assessment
from backend.report.pdf import build_pdf


def _run(req):
    return asyncio.run(run_assessment(req))


def test_demo_assessment_complete():
    a = _run(AssessRequest(lat=30.0444, lon=31.2357, project_name="Cairo Test"))
    assert isinstance(a, Assessment)
    assert a.data_mode == "live"
    assert a.project_name == "Cairo Test"
    assert a.soil.layers, "expected soil layers"
    assert a.parameters.allowable_bearing_kpa is not None
    assert a.parameters.settlement_mm is not None
    assert a.parameters.bearing_curve, "expected a bearing curve"
    assert a.parameters.seismic_site_class
    assert a.climate.annual_precip_mm is not None
    assert a.climate.frost_depth_m is not None
    assert a.vegetation.ndvi is not None
    assert a.vegetation.cover_class
    assert a.hydrology.nearest_water_m is not None
    assert a.suitability is not None
    assert 0 <= a.suitability.score <= 100
    assert a.suitability.rating in ("Favourable", "Marginal", "Challenging", "Severe")
    assert len(a.hazards) >= 5
    assert any(h.name == "Flooding / inundation" for h in a.hazards)
    assert a.recommendations
    assert a.disclaimer


def test_demo_is_deterministic():
    a1 = _run(AssessRequest(lat=10, lon=20))
    a2 = _run(AssessRequest(lat=10, lon=20))
    assert a1.parameters.allowable_bearing_kpa == a2.parameters.allowable_bearing_kpa
    assert a1.terrain.slope_deg == a2.terrain.slope_deg


def test_demo_varies_by_location():
    a1 = _run(AssessRequest(lat=10, lon=20))
    a2 = _run(AssessRequest(lat=-45, lon=170))
    assert (a1.terrain.slope_deg, a1.soil.dominant_usda_texture) != \
           (a2.terrain.slope_deg, a2.soil.dominant_usda_texture)


def test_place_demo_resolves():
    a = _run(AssessRequest(place="Nowhere Land"))
    assert a.location.lat is not None and a.location.lon is not None


def test_pdf_bytes_produced():
    a = _run(AssessRequest(lat=35.68, lon=139.69, project_name="Tokyo"))
    pdf = build_pdf(a)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 3000


def test_soil_nodata_is_unavailable_not_defaulted(monkeypatch):
    """SoilGrids 200 with all-null values must yield 'unavailable', never
    generic default parameters (no fabrication)."""
    import backend.services.soil as soilmod
    from backend.schemas import SoilProfile, SoilLayer

    async def nodata(client, lat, lon):
        return SoilProfile(source="ISRIC SoilGrids v2.0",
                           layers=[SoilLayer(depth_label="0-5cm", top_cm=0, bottom_cm=5)])

    monkeypatch.setattr(soilmod, "fetch_soil", nodata)
    a = _run(AssessRequest(lat=30, lon=31))
    assert a.parameters.data_basis == "unavailable"
    assert a.parameters.allowable_bearing_kpa is None
    assert any("no data at this exact point" in w for w in a.warnings)


def test_bad_request_raises():
    import pytest
    with pytest.raises(ValueError):
        _run(AssessRequest())
