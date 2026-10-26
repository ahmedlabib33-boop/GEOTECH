"""Wind & snow extremes from the Open-Meteo ERA5 reanalysis archive (no API key).

Pulls the multi-year DAILY 10 m wind-gust maxima (plus dominant wind direction)
and the HOURLY on-ground snow depth, reduces them to annual maxima, and hands
them to engineering.windsnow for a Gumbel extreme-value fit -> screening design
wind/snow loads. Real-only: a failed fetch is reported as unavailable and is
never replaced with synthetic data.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import httpx

from ..schemas import WindSnowStudy
from ..engineering.windsnow import build_windsnow

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
RECORD_YEARS = 15   # length of the extreme-value sample

# The hourly snow-depth series is large (~130k values over 15 yr); give the
# request a dedicated longer read timeout but keep it inside the 60 s budget.
_TIMEOUT = httpx.Timeout(connect=10.0, read=45.0, write=10.0, pool=10.0)

_SECTORS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def _dominant_direction(dirs: list[Optional[float]]) -> Optional[str]:
    """Modal 8-point compass sector of the daily dominant wind directions."""
    counts = [0] * 8
    for d in dirs:
        if d is None:
            continue
        idx = int(((d % 360) + 22.5) // 45) % 8
        counts[idx] += 1
    if not any(counts):
        return None
    return _SECTORS[counts.index(max(counts))]


def _annual_max(times: list[str], values: list) -> list[float]:
    """Reduce a (ISO-time, value) series to one maximum per calendar year."""
    by_year: dict[str, float] = {}
    for t, v in zip(times, values):
        if v is None or not t:
            continue
        yr = t[:4]
        if yr not in by_year or v > by_year[yr]:
            by_year[yr] = v
    return [by_year[y] for y in sorted(by_year)]


async def fetch_windsnow(client: httpx.AsyncClient, lat: float, lon: float) -> WindSnowStudy:
    end_yr = date.today().year - 1
    start_yr = end_yr - (RECORD_YEARS - 1)
    r = await client.get(
        ARCHIVE,
        params={
            "latitude": lat, "longitude": lon,
            "start_date": f"{start_yr}-01-01", "end_date": f"{end_yr}-12-31",
            "daily": "wind_gusts_10m_max,wind_direction_10m_dominant",
            "hourly": "snow_depth",
            "wind_speed_unit": "ms",
            "timezone": "auto",
        },
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    j = r.json()
    daily = j.get("daily", {}) or {}
    hourly = j.get("hourly", {}) or {}

    gust_annual = _annual_max(daily.get("time", []), daily.get("wind_gusts_10m_max", []))
    dominant = _dominant_direction(daily.get("wind_direction_10m_dominant", []))
    snow_annual = _annual_max(hourly.get("time", []), hourly.get("snow_depth", []))

    study = build_windsnow(
        wind_annual_max_gust_ms=gust_annual,
        snow_annual_max_depth_m=snow_annual,
        dominant_wind_dir=dominant,
        years=len(gust_annual) or len(snow_annual) or None,
    )
    if study is None:
        return WindSnowStudy(source="unavailable",
                             notes=["ERA5 returned no wind/snow extremes at this point."])
    study.source = (f"Open-Meteo ERA5 reanalysis {start_yr}-{end_yr}; "
                    "Gumbel extreme-value fit")
    return study
