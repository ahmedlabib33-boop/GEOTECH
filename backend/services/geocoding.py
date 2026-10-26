"""Geocoding + reverse geocoding via OpenStreetMap Nominatim (no API key)."""
from __future__ import annotations

from typing import Optional

import httpx

from ..schemas import Location

NOMINATIM = "https://nominatim.openstreetmap.org"


async def geocode(client: httpx.AsyncClient, place: str) -> Optional[Location]:
    """Resolve a free-text place name to a Location."""
    r = await client.get(
        f"{NOMINATIM}/search",
        params={"q": place, "format": "json", "limit": 1, "addressdetails": 1},
    )
    r.raise_for_status()
    data = r.json()
    if not data:
        return None
    hit = data[0]
    addr = hit.get("address", {}) or {}
    return Location(
        lat=float(hit["lat"]),
        lon=float(hit["lon"]),
        display_name=hit.get("display_name"),
        country=addr.get("country"),
    )


async def reverse(client: httpx.AsyncClient, lat: float, lon: float) -> Location:
    """Attach a human-readable name/country to a coordinate pair.

    Reverse geocoding is best-effort; failures degrade to bare coordinates.
    """
    loc = Location(lat=lat, lon=lon, display_name=f"{lat:.5f}, {lon:.5f}")
    try:
        r = await client.get(
            f"{NOMINATIM}/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 10},
        )
        r.raise_for_status()
        data = r.json()
        addr = data.get("address", {}) or {}
        if data.get("display_name"):
            loc.display_name = data["display_name"]
        loc.country = addr.get("country")
    except Exception:
        pass
    return loc
