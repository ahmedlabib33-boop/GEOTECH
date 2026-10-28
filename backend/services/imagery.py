"""Sentinel-2 imagery recency over a site — keyless (Copernicus Data Space).

Queries the Copernicus Data Space OData catalogue (no API key) for the most
recent Sentinel-2 L2A products intersecting the point, and reports how fresh the
latest pass is plus the most recent *usable* (low-cloud) pass. This is the
honest answer to "how live is the satellite image?" — imaging satellites revisit
a spot only every few days, so there is never a real-time view.

Bulletproof: any failure returns None (or a note), so it never breaks the
assessment.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import httpx

from ..schemas import SatelliteImagery

ODATA = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
WINDOW_DAYS = 120          # look back far enough to find a clear scene anywhere
CLEAR_CLOUD_PCT = 20.0     # "usable" = below this cloud cover


def _parse(products: list, today: date) -> Optional[SatelliteImagery]:
    """Reduce OData products to a recency summary. Pure (unit-testable)."""
    scenes: list[tuple[str, Optional[float]]] = []
    for p in products:
        start = (p.get("ContentDate") or {}).get("Start")
        if not start:
            continue
        day = start[:10]
        cloud = None
        for a in (p.get("Attributes") or []):
            if a.get("Name") == "cloudCover":
                try:
                    cloud = round(float(a.get("Value")), 1)
                except (TypeError, ValueError):
                    cloud = None
        scenes.append((day, cloud))
    if not scenes:
        return None
    scenes.sort(key=lambda s: s[0], reverse=True)

    def days_ago(day: str) -> Optional[int]:
        try:
            return (today - date.fromisoformat(day)).days
        except ValueError:
            return None

    out = SatelliteImagery(
        passes_in_window=len(scenes), window_days=WINDOW_DAYS,
        source="Sentinel-2 L2A catalogue (Copernicus Data Space, keyless)")
    latest = scenes[0]
    out.latest_pass_date = latest[0]
    out.latest_pass_cloud_pct = latest[1]
    out.latest_pass_days_ago = days_ago(latest[0])
    clear = next((s for s in scenes if s[1] is not None and s[1] < CLEAR_CLOUD_PCT), None)
    if clear:
        out.latest_clear_date = clear[0]
        out.latest_clear_cloud_pct = clear[1]
        out.latest_clear_days_ago = days_ago(clear[0])
    else:
        out.note = (f"No low-cloud (<{CLEAR_CLOUD_PCT:.0f}%) Sentinel-2 scene in the last "
                    f"{WINDOW_DAYS} days — the latest imagery may be cloud-obscured.")
    return out


async def fetch_imagery(lat: float, lon: float) -> Optional[SatelliteImagery]:
    start = date.fromordinal(date.today().toordinal() - WINDOW_DAYS)
    params = {
        "$filter": (
            "Collection/Name eq 'SENTINEL-2' and "
            f"OData.CSC.Intersects(area=geography'SRID=4326;POINT({lon} {lat})') and "
            "contains(Name,'MSIL2A') and "
            f"ContentDate/Start gt {start}T00:00:00.000Z"),
        "$orderby": "ContentDate/Start desc",
        "$top": "50",
        "$expand": "Attributes",
    }
    try:
        timeout = httpx.Timeout(connect=8.0, read=15.0, write=10.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True,
                                     headers={"Accept": "application/json"}) as client:
            r = await client.get(ODATA, params=params)
            r.raise_for_status()
            products = r.json().get("value", [])
    except Exception:
        return None
    return _parse(products, date.today())
