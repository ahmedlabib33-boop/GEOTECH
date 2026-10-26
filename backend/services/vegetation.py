"""Vegetation / NDVI from the NASA ORNL DAAC MODIS REST API (no API key).

Uses MOD13Q1 (Terra, 250 m, 16-day NDVI). NDVI is a satellite vegetation index
(from Sentinel-2/MODIS red & near-infrared bands) that, for a geotechnical desk
study, flags organic topsoil / clearing effort, surface-erosion exposure, slope
root-reinforcement, and a near-surface moisture signal (relevant to expansive
clays).
"""
from __future__ import annotations

from typing import Optional

import httpx

from ..schemas import Vegetation

BASE = "https://modis.ornl.gov/rst/api/v1"
PRODUCT = "MOD13Q1"
BAND = "250m_16_days_NDVI"
SCALE = 0.0001
FILL_MIN = -0.2  # values below this are cloud/water/fill


def cover_class(ndvi: float) -> tuple[str, str]:
    """Return (cover_class, ground_description) for a geotech reading."""
    if ndvi < 0.1:
        return ("Barren / non-vegetated",
                "Bare rock, soil, sand, urban or water — minimal organic topsoil; "
                "check for near-surface rock or impervious cover.")
    if ndvi < 0.3:
        return ("Sparse vegetation",
                "Thin or patchy cover — expect a shallow organic topsoil layer to "
                "strip; moderate surface-erosion exposure.")
    if ndvi < 0.6:
        return ("Moderate vegetation",
                "Grass/shrub/crops — organic topsoil present (strip before founding); "
                "roots give some slope reinforcement.")
    return ("Dense vegetation",
            "Forest/dense canopy — significant clearing and topsoil stripping; strong "
            "root reinforcement but also a wetter, organic-rich near surface.")


async def fetch_vegetation(client: httpx.AsyncClient, lat: float, lon: float) -> Vegetation:
    # 1) available acquisition dates for this pixel
    dr = await client.get(f"{BASE}/{PRODUCT}/dates",
                          params={"latitude": lat, "longitude": lon})
    dr.raise_for_status()
    dates = dr.json().get("dates", [])
    if not dates:
        return Vegetation(source="NASA ORNL MODIS (MOD13Q1)",
                          note="No MODIS coverage at this location.")

    recent = dates[-6:] if len(dates) >= 6 else dates
    start = recent[0]["modis_date"]
    end = recent[-1]["modis_date"]

    # 2) NDVI subset over the recent window (single pixel)
    sr = await client.get(
        f"{BASE}/{PRODUCT}/subset",
        params={"latitude": lat, "longitude": lon, "band": BAND,
                "startDate": start, "endDate": end,
                "kmAboveBelow": 0, "kmLeftRight": 0},
    )
    sr.raise_for_status()
    body = sr.json()
    scale = float(body.get("scale") or SCALE)

    valid: list[tuple[str, float]] = []
    for entry in body.get("subset", []):
        data = entry.get("data") or []
        if not data or data[0] is None:
            continue
        v = float(data[0]) * scale
        if v >= FILL_MIN:
            valid.append((entry.get("calendar_date", ""), round(v, 3)))

    if not valid:
        return Vegetation(source="NASA ORNL MODIS (MOD13Q1)",
                          note="Recent observations were cloud/snow-obscured.")

    # Use the most recent valid observation.
    date, ndvi = sorted(valid, key=lambda x: x[0])[-1]
    cls, desc = cover_class(ndvi)
    return Vegetation(
        ndvi=ndvi, observation_date=date, cover_class=cls, ground_description=desc,
        source="NASA ORNL MODIS (MOD13Q1, 250 m NDVI)",
    )
