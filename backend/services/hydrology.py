"""Water proximity + riverine flood signal (no API key).

- Nearest surface water (river / lake / reservoir / coastline) from the
  OpenStreetMap Overpass API.
- River discharge (GloFAS) from the Open-Meteo Flood API as a riverine-flood
  magnitude indicator.

Both are best-effort: either can be slow or unavailable, and the flood-hazard
screening still works from terrain + rainfall alone if they are missing.
"""
from __future__ import annotations

import math
from typing import Optional

import httpx

from ..schemas import Hydrology, Terrain

OVERPASS = "https://overpass-api.de/api/interpreter"
FLOOD_API = "https://flood-api.open-meteo.com/v1/flood"
SEARCH_RADIUS_M = 5000


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _describe(tags: dict) -> str:
    if tags.get("natural") == "coastline":
        return "coastline / sea"
    if tags.get("natural") == "water" or tags.get("water"):
        return tags.get("water") or "lake / pond / reservoir"
    wt = tags.get("waterway")
    if wt:
        return f"{wt}"
    return "water body"


async def _nearest_water(client: httpx.AsyncClient, lat: float, lon: float):
    q = f"""
    [out:json][timeout:20];
    (
      way(around:{SEARCH_RADIUS_M},{lat},{lon})[natural=water];
      way(around:{SEARCH_RADIUS_M},{lat},{lon})[waterway~"river|stream|canal"];
      way(around:{SEARCH_RADIUS_M},{lat},{lon})[natural=coastline];
      node(around:{SEARCH_RADIUS_M},{lat},{lon})[natural=water];
    );
    out tags center 40;
    """
    r = await client.post(OVERPASS, data={"data": q})
    r.raise_for_status()
    elements = r.json().get("elements", [])
    best = None
    for el in elements:
        c = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
        if c.get("lat") is None or c.get("lon") is None:
            continue
        d = _haversine_m(lat, lon, c["lat"], c["lon"])
        if best is None or d < best[0]:
            best = (d, c["lat"], c["lon"], _describe(el.get("tags", {})))
    return best


async def _river_discharge(client: httpx.AsyncClient, lat: float, lon: float):
    r = await client.get(FLOOD_API, params={
        "latitude": lat, "longitude": lon,
        "daily": "river_discharge", "forecast_days": 1, "past_days": 31})
    r.raise_for_status()
    vals = [v for v in (r.json().get("daily", {}).get("river_discharge") or [])
            if v is not None]
    return round(max(vals), 1) if vals else None


async def fetch_hydrology(client: httpx.AsyncClient, lat: float, lon: float,
                          terrain: Optional[Terrain] = None) -> Hydrology:
    h = Hydrology(source="OpenStreetMap Overpass + Open-Meteo Flood (GloFAS)")
    try:
        near = await _nearest_water(client, lat, lon)
        if near:
            d, wlat, wlon, desc = near
            h.nearest_water_m = round(d, 0)
            h.nearest_water_lat = round(wlat, 6)
            h.nearest_water_lon = round(wlon, 6)
            h.nearest_water_type = desc
        else:
            h.note = f"No mapped surface water within {SEARCH_RADIUS_M/1000:.0f} km."
    except Exception:
        h.note = "Water-proximity lookup unavailable."

    try:
        h.river_discharge_m3s = await _river_discharge(client, lat, lon)
    except Exception:
        pass

    if terrain and terrain.elevation_m is not None:
        h.height_above_water_m = terrain.elevation_m  # ground elevation proxy
    return h
