"""InSAR ground-motion velocity (subsidence / uplift).

Sources, in priority order:
  1. A measured value supplied with the request (e.g. from an EGMS download or a
     commercial/processed InSAR dataset).
  2. An optional point-query provider configured via INSAR_API_URL — a URL with
     {lat}/{lon} placeholders returning JSON containing a velocity in mm/yr.

There is no free, no-login, global live InSAR point API, so without one of the
above the layer reports "no InSAR source" and links to the EGMS viewer (Europe).
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

from ..schemas import GroundMotion

INSAR_API_URL = os.environ.get("INSAR_API_URL")  # e.g. ".../insar?lat={lat}&lon={lon}"
_VELOCITY_KEYS = ("velocity_mm_yr", "velocity", "los_velocity", "vel", "mean_velocity")


def _in_europe(lat: float, lon: float) -> bool:
    return 34 <= lat <= 72 and -25 <= lon <= 45


def _egms_url(lat: float, lon: float) -> Optional[str]:
    if not _in_europe(lat, lon):
        return None
    return f"https://egms.land.copernicus.eu/insar-viewer/map/?lat={lat:.5f}&lon={lon:.5f}&z=14"


def classify(v: Optional[float]) -> tuple[Optional[str], Optional[str]]:
    """Return (direction, note) for a signed velocity (mm/yr)."""
    if v is None:
        return None, None
    mag = abs(v)
    direction = "stable" if mag < 2 else ("subsidence" if v < 0 else "uplift")
    if mag < 2:
        note = "Ground essentially stable."
    elif mag < 10:
        note = f"Mild {direction} (~{mag:.0f} mm/yr) — monitor for differential movement."
    elif mag < 30:
        note = (f"Significant {direction} (~{mag:.0f} mm/yr) — risk of differential "
                "settlement/heave and services damage; investigate the cause.")
    else:
        note = (f"Severe {direction} (~{mag:.0f} mm/yr) — major ground-movement hazard; "
                "detailed monitoring and specialist assessment required.")
    return direction, note


async def _from_provider(lat: float, lon: float) -> Optional[float]:
    if not INSAR_API_URL:
        return None
    url = INSAR_API_URL.replace("{lat}", f"{lat}").replace("{lon}", f"{lon}")
    try:
        timeout = httpx.Timeout(connect=8.0, read=20.0, write=8.0, pool=8.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
        if isinstance(data, dict):
            for k in _VELOCITY_KEYS:
                if k in data and data[k] is not None:
                    return float(data[k])
    except Exception:
        return None
    return None


async def fetch_ground_motion(lat: float, lon: float,
                              measured: Optional[float] = None) -> Optional[GroundMotion]:
    velocity = measured
    source = None
    if velocity is not None:
        source = "User-supplied InSAR velocity (measured)"
    else:
        velocity = await _from_provider(lat, lon)
        if velocity is not None:
            source = "InSAR provider (INSAR_API_URL)"

    viewer = _egms_url(lat, lon)
    if velocity is None:
        if viewer is None:
            return None  # nothing to show outside Europe with no source
        return GroundMotion(
            source="No InSAR velocity supplied",
            note="No measured InSAR value or provider configured. Europe: open the "
                 "EGMS viewer for measured ground motion at this point.",
            egms_viewer_url=viewer)

    direction, note = classify(velocity)
    return GroundMotion(velocity_mm_yr=round(velocity, 1), direction=direction,
                        note=note, source=source, egms_viewer_url=viewer)
