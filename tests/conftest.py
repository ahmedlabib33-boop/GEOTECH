"""Offline test harness: patch the live data services with deterministic fakes
so the full pipeline/endpoints run without network. The product has no demo
mode; these fakes live only in the test suite.
"""
import pytest

from backend.schemas import GroundMotion
from backend.services.groundmotion import classify, _egms_url
from tests import fakes


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    import backend.services.terrain as terrain
    import backend.services.soil as soil
    import backend.services.seismic as seismic
    import backend.services.climate as climate
    import backend.services.vegetation as vegetation
    import backend.services.hydrology as hydrology
    import backend.services.windsnow as windsnow
    import backend.services.logistics as logistics
    import backend.services.cache as cache
    import backend.services.sentinelhub as sentinelhub

    cache.clear()  # isolate the in-process data cache between tests
    import backend.services.groundmotion as groundmotion
    import backend.services.geocoding as geocoding
    import backend.main as main

    async def t(client, lat, lon): return fakes.fake_terrain(lat, lon)
    async def s(client, lat, lon): return fakes.fake_soil(lat, lon)
    async def q(client, lat, lon): return fakes.fake_seismic(lat, lon)
    async def c(client, lat, lon): return fakes.fake_climate(lat, lon)
    async def v(client, lat, lon): return fakes.fake_vegetation(lat, lon)
    async def h(client, lat, lon, terrain=None): return fakes.fake_hydrology(lat, lon)
    async def ws(client, lat, lon): return fakes.fake_windsnow(lat, lon)
    async def lo(client, lat, lon): return fakes.fake_logistics(lat, lon)
    async def rev(client, lat, lon): return fakes.fake_location(lat, lon)
    async def geo(client, place): return fakes.fake_location(10.0, 20.0)
    async def sh(lat, lon): return None
    async def gm(lat, lon, measured=None):
        if measured is None:
            return None
        d, note = classify(measured)
        return GroundMotion(velocity_mm_yr=measured, direction=d, note=note,
                            source="User-supplied InSAR velocity (measured)",
                            egms_viewer_url=_egms_url(lat, lon))
    async def img(lat, lon, zoom=16, grid=3): return None

    monkeypatch.setattr(terrain, "fetch_terrain", t)
    monkeypatch.setattr(soil, "fetch_soil", s)
    monkeypatch.setattr(seismic, "fetch_seismic", q)
    monkeypatch.setattr(climate, "fetch_climate", c)
    monkeypatch.setattr(vegetation, "fetch_vegetation", v)
    monkeypatch.setattr(hydrology, "fetch_hydrology", h)
    monkeypatch.setattr(windsnow, "fetch_windsnow", ws)
    monkeypatch.setattr(logistics, "fetch_logistics", lo)
    monkeypatch.setattr(geocoding, "reverse", rev)
    monkeypatch.setattr(geocoding, "geocode", geo)
    monkeypatch.setattr(sentinelhub, "fetch_sentinel", sh)
    monkeypatch.setattr(groundmotion, "fetch_ground_motion", gm)
    monkeypatch.setattr(main, "site_image", img)
    yield
