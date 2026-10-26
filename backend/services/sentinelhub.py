"""Sentinel-2 10 m indices via Sentinel Hub (Copernicus Data Space Ecosystem).

Uses the OAuth client-credentials flow + the Statistical API to return the mean
NDVI / NDWI / NDMI in a small window around the site at 10 m resolution. Enabled
only when SENTINELHUB_CLIENT_ID / SENTINELHUB_CLIENT_SECRET are configured;
returns None on missing credentials or any error so the rest of the report is
unaffected.

Free credentials: register at https://dataspace.copernicus.eu/ and create an
OAuth client (Sentinel Hub -> User settings -> OAuth clients).
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Optional

import httpx

from ..schemas import SentinelHR

TOKEN_URL = os.environ.get(
    "SENTINELHUB_TOKEN_URL",
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token")
STATS_URL = os.environ.get(
    "SENTINELHUB_STATS_URL",
    "https://sh.dataspace.copernicus.eu/api/v1/statistics")

_EVALSCRIPT = """//VERSION=3
function setup() {
  return {
    input: [{bands: ["B03","B04","B08","B11","SCL","dataMask"]}],
    output: [
      {id: "ndvi", bands: 1, sampleType: "FLOAT32"},
      {id: "ndwi", bands: 1, sampleType: "FLOAT32"},
      {id: "ndmi", bands: 1, sampleType: "FLOAT32"},
      {id: "dataMask", bands: 1}
    ]
  };
}
function evaluatePixel(s) {
  let ndvi = (s.B08 - s.B04) / (s.B08 + s.B04);
  let ndwi = (s.B03 - s.B08) / (s.B03 + s.B08);
  let ndmi = (s.B08 - s.B11) / (s.B08 + s.B11);
  let cloud = (s.SCL==3 || s.SCL==8 || s.SCL==9 || s.SCL==10 || s.SCL==11);
  let valid = (s.dataMask==1 && !cloud) ? 1 : 0;
  return {ndvi:[ndvi], ndwi:[ndwi], ndmi:[ndmi], dataMask:[valid]};
}
"""


def available() -> bool:
    return bool(os.environ.get("SENTINELHUB_CLIENT_ID")
               and os.environ.get("SENTINELHUB_CLIENT_SECRET"))


async def _token(client: httpx.AsyncClient) -> Optional[str]:
    r = await client.post(TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": os.environ["SENTINELHUB_CLIENT_ID"],
        "client_secret": os.environ["SENTINELHUB_CLIENT_SECRET"],
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    r.raise_for_status()
    return r.json().get("access_token")


def _mean(outputs: dict, name: str) -> Optional[float]:
    try:
        stats = outputs[name]["bands"]["B0"]["stats"]
        if stats.get("sampleCount", 0) - stats.get("noDataCount", 0) <= 0:
            return None
        return stats.get("mean")
    except Exception:
        return None


async def fetch_sentinel(lat: float, lon: float) -> Optional[SentinelHR]:
    if not available():
        return None
    d = 0.00015  # ~16 m half-window
    bbox = [lon - d, lat - d, lon + d, lat + d]
    today = date.today()
    start = today - timedelta(days=120)
    body = {
        "input": {
            "bounds": {"bbox": bbox,
                       "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}},
            "data": [{"type": "sentinel-2-l2a",
                      "dataFilter": {"mosaickingOrder": "leastCC"}}],
        },
        "aggregation": {
            "timeRange": {"from": f"{start}T00:00:00Z", "to": f"{today}T23:59:59Z"},
            "aggregationInterval": {"of": "P30D"},
            "resx": 10, "resy": 10,
            "evalscript": _EVALSCRIPT,
        },
    }
    try:
        timeout = httpx.Timeout(connect=10.0, read=40.0, write=10.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            tok = await _token(client)
            if not tok:
                return None
            r = await client.post(STATS_URL, json=body,
                                  headers={"Authorization": f"Bearer {tok}"})
            r.raise_for_status()
            data = r.json().get("data", [])
    except Exception:
        return None

    # Most recent interval that has valid (cloud-free) pixels.
    for item in sorted(data, key=lambda x: x.get("interval", {}).get("to", ""), reverse=True):
        outputs = item.get("outputs", {})
        ndvi = _mean(outputs, "ndvi")
        if ndvi is None:
            continue
        dm = outputs.get("dataMask", {}).get("bands", {}).get("B0", {}).get("stats", {})
        valid_frac = dm.get("mean")
        return SentinelHR(
            ndvi=round(ndvi, 3),
            ndwi=_round(_mean(outputs, "ndwi")),
            ndmi=_round(_mean(outputs, "ndmi")),
            observation_date=(item.get("interval", {}).get("to", "") or "")[:10] or None,
            valid_fraction=_round(valid_frac, 2),
            source="Sentinel-2 L2A 10 m (Sentinel Hub / Copernicus)",
        )
    return SentinelHR(source="Sentinel-2 (Sentinel Hub)",
                      note="No cloud-free Sentinel-2 scene in the last 120 days.")


def _round(v, n: int = 3):
    return None if v is None else round(v, n)
