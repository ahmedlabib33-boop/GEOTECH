"""Endpoint-level tests via FastAPI TestClient (demo mode, no network)."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.http import with_retry

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "ai_available" in body and "sentinelhub_available" in body


def test_index_served():
    assert client.get("/").status_code == 200


def test_assess_demo_ok():
    r = client.post("/api/assess?demo=true",
                    json={"lat": 30.04, "lon": 31.23, "project_name": "API Test"})
    assert r.status_code == 200
    a = r.json()
    assert a["data_mode"] == "demo"
    assert a["suitability"]["rating"] in ("Favourable", "Marginal", "Challenging", "Severe")
    assert a["parameters"]["allowable_bearing_kpa"] is not None


def test_assess_missing_coords_400():
    assert client.post("/api/assess?demo=true", json={}).status_code == 400


def test_assess_bad_lat_422():
    assert client.post("/api/assess?demo=true", json={"lat": 200, "lon": 0}).status_code == 422


def test_report_pdf_demo():
    r = client.post("/api/report.pdf?demo=true", json={"lat": 35, "lon": 25})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
    assert r.headers["content-type"] == "application/pdf"


def test_compare_pdf():
    a = client.post("/api/assess?demo=true", json={"lat": 35, "lon": 25, "project_name": "A"}).json()
    b = client.post("/api/assess?demo=true", json={"lat": -20, "lon": 140, "project_name": "B"}).json()
    r = client.post("/api/compare.pdf", json={"sites": [a, b]})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_compare_pdf_needs_two():
    a = client.post("/api/assess?demo=true", json={"lat": 35, "lon": 25}).json()
    assert client.post("/api/compare.pdf", json={"sites": [a]}).status_code == 400


def test_borehole_override_via_api():
    r = client.post("/api/assess?demo=true", json={
        "lat": 1.35, "lon": 103.8, "foundation_depth_m": 1.5,
        "borehole": {"groundwater_depth_m": 2.0, "layers": [
            {"top_m": 0, "bottom_m": 8, "description": "dense SAND", "uscs": "SP", "spt_n": 30}]}})
    assert r.status_code == 200
    assert r.json()["parameters"]["data_basis"] == "borehole"


# --- retry helper behaviour ---
def test_with_retry_succeeds_after_transient():
    import httpx
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.ConnectError("boom")
        return "ok"

    assert asyncio.run(with_retry(flaky, attempts=2, base_delay=0)) == "ok"
    assert calls["n"] == 2


def test_with_retry_does_not_retry_4xx():
    import httpx
    calls = {"n": 0}

    async def notfound():
        calls["n"] += 1
        resp = httpx.Response(404, request=httpx.Request("GET", "http://x"))
        raise httpx.HTTPStatusError("nf", request=resp.request, response=resp)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(with_retry(notfound, attempts=3, base_delay=0))
    assert calls["n"] == 1  # 4xx not retried
