"""Site logistics & access from OpenStreetMap (Overpass, no API key).

For an overseas bid the mobilization and supply-chain cost drivers are the
distances to the nearest seaport (import of plant/materials), airport, major
road (site access), railway, urban centre (labour/lodging/supply), aggregate
quarry and power grid. This queries OSM once and reports the nearest of each,
plus an overall mobilization-complexity rating. Real-only: a category with
nothing mapped within its search radius is reported as such, never invented.
"""
from __future__ import annotations

import math
from typing import Optional

import httpx

from ..schemas import LogisticsPOI, SiteLogistics

# A mirror distinct from hydrology's (overpass-api.de) to avoid per-IP contention.
OVERPASS = "https://overpass.kumi.systems/api/interpreter"
_TIMEOUT = httpx.Timeout(connect=10.0, read=50.0, write=10.0, pool=10.0)

# (kind, radius_m) per category.
_PORT_R, _AIR_R, _ROAD_R, _RAIL_R, _URBAN_R, _QUARRY_R, _POWER_R = (
    300_000, 200_000, 25_000, 120_000, 120_000, 80_000, 40_000)


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
    return f"""
    [out:json][timeout:50];
    (
      nwr(around:{_PORT_R},{lat},{lon})[harbour];
      nwr(around:{_PORT_R},{lat},{lon})[industrial=port];
      nwr(around:{_PORT_R},{lat},{lon})[landuse=harbour];
      nwr(around:{_PORT_R},{lat},{lon})[amenity=ferry_terminal];
      nwr(around:{_AIR_R},{lat},{lon})[aeroway=aerodrome];
      way(around:{_ROAD_R},{lat},{lon})[highway~"^(motorway|trunk|primary)$"];
      nwr(around:{_RAIL_R},{lat},{lon})[railway~"^(station|halt)$"];
      nwr(around:{_URBAN_R},{lat},{lon})[place~"^(city|town)$"];
      nwr(around:{_QUARRY_R},{lat},{lon})[landuse=quarry];
      nwr(around:{_POWER_R},{lat},{lon})[power=substation];
    );
    out tags center 400;
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
    bits.append("no seaport within 300 km" if port is None else f"port ~{port:.0f} km")
    bits.append("no major road within 25 km" if road is None else f"major road ~{road:.0f} km")
    bits.append("no town within 120 km" if urban is None else f"town ~{urban:.0f} km")
    return rating, "; ".join(bits)


async def fetch_logistics(client: httpx.AsyncClient, lat: float, lon: float) -> SiteLogistics:
    out = SiteLogistics(source="OpenStreetMap Overpass")
    try:
        r = await client.post(OVERPASS, data={"data": _query(lat, lon)}, timeout=_TIMEOUT)
        r.raise_for_status()
        elements = r.json().get("elements", [])
    except Exception:
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
