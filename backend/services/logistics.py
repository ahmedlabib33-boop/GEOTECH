"""Site logistics & access from OpenStreetMap (Overpass, no API key).

For an overseas bid the mobilization and supply-chain cost drivers are the
distances to the nearest seaport (import of plant/materials), airport, major
road (site access), railway, urban centre (labour/lodging/supply), aggregate
quarry and power grid. This queries OSM once and reports the nearest of each,
plus an overall mobilization-complexity rating. Real-only: a category with
nothing mapped within its search radius is reported as such, never invented.
"""
from __future__ import annotations

import asyncio
import math
from typing import Optional

import httpx

from ..schemas import LogisticsPOI, SiteLogistics

# Same endpoint hydrology uses (proven reachable); Overpass queues the two
# queries per IP. A moderate timeout keeps a slow response from dominating the
# 60 s function budget — on failure the layer degrades to a note (real-only).
OVERPASS = "https://overpass-api.de/api/interpreter"
# Lean query answers fast; a short read keeps two attempts inside the 60 s budget.
_TIMEOUT = httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=10.0)

# (kind, radius_m) per category. Kept modest so the Overpass scan is light and
# returns quickly; sparse, high-value features (ports/airports) still get range.
_PORT_R, _AIR_R, _ROAD_R, _RAIL_R, _URBAN_R, _QUARRY_R, _POWER_R = (
    120_000, 100_000, 12_000, 60_000, 80_000, 40_000, 25_000)


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _classify(tags: dict) -> Optional[str]:
    if (tags.get("harbour") or tags.get("industrial") == "port"
            or tags.get("landuse") == "harbour" or tags.get("amenity") == "ferry_terminal"
            or tags.get("seamark:type") == "harbour"):
        return "seaport"
    if tags.get("aeroway") == "aerodrome":
        return "airport"
    if tags.get("highway") in ("motorway", "trunk", "primary"):
        return "major_road"
    if tags.get("railway") in ("station", "halt"):
        return "railway"
    if tags.get("place") in ("city", "town"):
        return "urban_centre"
    if tags.get("landuse") == "quarry":
        return "quarry"
    if tags.get("power") == "substation":
        return "power"
    return None


def _query(lat: float, lon: float) -> str:
    # Nodes where the feature is usually a node (place, rail, ferry) to keep the
    # query cheap; ways/relations only where needed (roads, quarries, aerodromes,
    # harbours), each with a tight result cap.
    return f"""
    [out:json][timeout:18];
    (
      nwr(around:{_PORT_R},{lat},{lon})[harbour];
      node(around:{_PORT_R},{lat},{lon})[amenity=ferry_terminal];
      nwr(around:{_AIR_R},{lat},{lon})[aeroway=aerodrome];
      way(around:{_ROAD_R},{lat},{lon})[highway~"^(motorway|trunk|primary)$"];
      node(around:{_RAIL_R},{lat},{lon})[railway=station];
      node(around:{_URBAN_R},{lat},{lon})[place~"^(city|town)$"];
      nwr(around:{_QUARRY_R},{lat},{lon})[landuse=quarry];
      nwr(around:{_POWER_R},{lat},{lon})[power=substation];
    );
    out tags center 60;
    """


def _rating(port, road, urban) -> tuple[str, str]:
    def band(v, cuts):
        if v is None:
            return len(cuts)
        for i, c in enumerate(cuts):
            if v < c:
                return i
        return len(cuts)
    score = (band(port, [100, 250, 400]) + band(road, [10, 25, 50])
             + band(urban, [25, 60, 100]))
    rating = ("Easy" if score <= 1 else "Moderate" if score <= 4
              else "Difficult" if score <= 7 else "Remote")
    bits = []
    bits.append("no seaport within 120 km" if port is None else f"port ~{port:.0f} km")
    bits.append("no major road within 12 km" if road is None else f"major road ~{road:.0f} km")
    bits.append("no town within 80 km" if urban is None else f"town ~{urban:.0f} km")
    return rating, "; ".join(bits)


async def fetch_logistics(client: httpx.AsyncClient, lat: float, lon: float) -> SiteLogistics:
    out = SiteLogistics(source="OpenStreetMap Overpass")
    q = _query(lat, lon)
    elements = None
    for attempt in range(2):   # Overpass can briefly reject a concurrent query
        try:
            r = await client.post(OVERPASS, data={"data": q}, timeout=_TIMEOUT)
            r.raise_for_status()
            elements = r.json().get("elements", [])
            break
        except Exception:
            if attempt == 0:
                await asyncio.sleep(1.5)
    if elements is None:
        out.note = "Logistics lookup (OSM Overpass) unavailable at this time."
        return out

    nearest: dict[str, LogisticsPOI] = {}
    for el in elements:
        kind = _classify(el.get("tags", {}))
        if not kind:
            continue
        c = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
        if c.get("lat") is None or c.get("lon") is None:
            continue
        d = _haversine_km(lat, lon, c["lat"], c["lon"])
        cur = nearest.get(kind)
        if cur is None or d < cur.distance_km:
            nearest[kind] = LogisticsPOI(
                kind=kind, name=(el.get("tags", {}).get("name") or None),
                distance_km=round(d, 1), lat=round(c["lat"], 5), lon=round(c["lon"], 5),
                detail=(el.get("tags", {}).get("highway") if kind == "major_road" else None))

    order = ["seaport", "airport", "major_road", "railway", "urban_centre", "quarry", "power"]
    out.pois = [nearest[k] for k in order if k in nearest]
    out.nearest_port_km = nearest["seaport"].distance_km if "seaport" in nearest else None
    out.nearest_airport_km = nearest["airport"].distance_km if "airport" in nearest else None
    out.nearest_major_road_km = nearest["major_road"].distance_km if "major_road" in nearest else None
    out.nearest_urban_km = nearest["urban_centre"].distance_km if "urban_centre" in nearest else None
    out.mobilization_rating, out.access_note = _rating(
        out.nearest_port_km, out.nearest_major_road_km, out.nearest_urban_km)
    return out
