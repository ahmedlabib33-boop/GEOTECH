"""Terrain analysis from a Digital Elevation Model (OpenTopoData / SRTM).

We sample a 3x3 grid of elevations around the target point and derive slope and
aspect with the Horn (1981) finite-difference method, the same approach GIS
packages use for raster terrain analysis.
"""
from __future__ import annotations

import math
from typing import Optional

import httpx

from ..schemas import Terrain

OPENTOPODATA = "https://api.opentopodata.org/v1"
# SRTM 30m is a good global default; falls back to ASTER/other inside the API.
DATASET = "srtm30m"
GRID_SPACING_M = 90.0  # neighbourhood half-step for slope estimation


def _classify_terrain(slope_deg: Optional[float]) -> Optional[str]:
    if slope_deg is None:
        return None
    if slope_deg < 2:
        return "Flat / level ground"
    if slope_deg < 5:
        return "Gently sloping"
    if slope_deg < 10:
        return "Moderately sloping"
    if slope_deg < 20:
        return "Strongly sloping / hilly"
    if slope_deg < 30:
        return "Steep"
    return "Very steep / mountainous"


def _grid_points(lat: float, lon: float, spacing_m: float):
    """Return a 3x3 grid (row-major, north->south) of (lat, lon)."""
    dlat = spacing_m / 111_320.0
    dlon = spacing_m / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
    rows = []
    for r in (1, 0, -1):          # north, centre, south
        for c in (-1, 0, 1):      # west, centre, east
            rows.append((lat + r * dlat, lon + c * dlon))
    return rows


def _slope_aspect(z, spacing_m: float):
    """Horn's method on a 3x3 window. `z` is 9 elevations row-major (N->S)."""
    # a b c
    # d e f
    # g h i
    a, b, c, d, e, f, g, h, i = z
    dz_dx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * spacing_m)
    dz_dy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * spacing_m)
    rise_run = math.sqrt(dz_dx ** 2 + dz_dy ** 2)
    slope_deg = math.degrees(math.atan(rise_run))
    aspect = math.degrees(math.atan2(dz_dy, -dz_dx))
    aspect = (450.0 - aspect) % 360.0  # convert to compass bearing
    return slope_deg, aspect


async def fetch_terrain(client: httpx.AsyncClient, lat: float, lon: float) -> Terrain:
    pts = _grid_points(lat, lon, GRID_SPACING_M)
    locs = "|".join(f"{a:.6f},{b:.6f}" for a, b in pts)
    r = await client.get(
        f"{OPENTOPODATA}/{DATASET}",
        params={"locations": locs, "interpolation": "bilinear"},
    )
    r.raise_for_status()
    results = r.json().get("results", [])
    elevs = [res.get("elevation") for res in results]
    if len(elevs) != 9 or any(v is None for v in elevs):
        # Partial coverage (e.g. ocean / void). Report what we can.
        centre = elevs[4] if len(elevs) > 4 else None
        valid = [v for v in elevs if v is not None]
        return Terrain(
            elevation_m=centre,
            relief_m=(max(valid) - min(valid)) if len(valid) > 1 else None,
            source="OpenTopoData (SRTM 30m)",
            note="Incomplete DEM coverage; slope not computed.",
        )

    slope_deg, aspect = _slope_aspect(elevs, GRID_SPACING_M)
    return Terrain(
        elevation_m=round(elevs[4], 1),
        slope_deg=round(slope_deg, 2),
        aspect_deg=round(aspect, 1),
        relief_m=round(max(elevs) - min(elevs), 2),
        terrain_class=_classify_terrain(slope_deg),
        source="OpenTopoData (SRTM 30m)",
    )
