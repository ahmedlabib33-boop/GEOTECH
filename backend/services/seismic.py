"""Seismic context from the USGS earthquake catalogue (FDSN, no API key).

This is a *historical seismicity* screen, not a code-based seismic hazard
analysis. It flags how active the region has been and gives an order-of-
magnitude ground-acceleration proxy to prompt a proper site-specific study.
"""
from __future__ import annotations

import math
from typing import Optional

import httpx

from ..schemas import SeismicContext

USGS = "https://earthquake.usgs.gov/fdsnws/event/1/query"
SEARCH_RADIUS_KM = 300.0
MIN_MAGNITUDE = 4.0


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _hazard_from(max_mag: Optional[float], count: int, nearest_km: Optional[float]) -> str:
    if max_mag is None or count == 0:
        return "Low (no significant historical events within search radius)"
    near = nearest_km if nearest_km is not None else 999
    if max_mag >= 7.0 and near < 150:
        return "Very High"
    if max_mag >= 6.0 and near < 200:
        return "High"
    if max_mag >= 5.0:
        return "Moderate"
    return "Low to Moderate"


def _pga_proxy(max_mag: Optional[float], nearest_km: Optional[float]) -> Optional[float]:
    """Crude Mw/distance attenuation -> PGA(g). Indicative only."""
    if max_mag is None or nearest_km is None:
        return None
    d = max(nearest_km, 5.0)
    # Simplified attenuation form; deliberately conservative/indicative.
    ln_pga = -3.512 + 0.904 * max_mag - 1.328 * math.log(math.sqrt(d ** 2 + 36))
    return round(math.exp(ln_pga), 3)


async def fetch_seismic(client: httpx.AsyncClient, lat: float, lon: float) -> SeismicContext:
    r = await client.get(
        USGS,
        params={
            "format": "geojson",
            "latitude": lat,
            "longitude": lon,
            "maxradiuskm": SEARCH_RADIUS_KM,
            "minmagnitude": MIN_MAGNITUDE,
            "orderby": "magnitude",
            "limit": 500,
        },
    )
    r.raise_for_status()
    features = r.json().get("features", [])

    ctx = SeismicContext(
        search_radius_km=SEARCH_RADIUS_KM,
        event_count=len(features),
        source="USGS Earthquake Catalog (FDSN)",
    )
    if not features:
        ctx.hazard_level = _hazard_from(None, 0, None)
        ctx.note = f"No M≥{MIN_MAGNITUDE} events within {SEARCH_RADIUS_KM:.0f} km."
        return ctx

    largest = features[0]
    mag = largest["properties"].get("mag")
    ctx.max_magnitude = mag
    ctx.largest_event_desc = largest["properties"].get("place")

    nearest = None
    for feat in features:
        coords = feat.get("geometry", {}).get("coordinates", [None, None])
        elon, elat = coords[0], coords[1]
        if elon is None or elat is None:
            continue
        d = _haversine_km(lat, lon, elat, elon)
        if nearest is None or d < nearest:
            nearest = d
    ctx.nearest_significant_km = None if nearest is None else round(nearest, 1)
    ctx.hazard_level = _hazard_from(mag, len(features), nearest)
    ctx.estimated_pga_g = _pga_proxy(mag, nearest)
    return ctx
