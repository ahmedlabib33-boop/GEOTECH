"""Climate normals from the Open-Meteo ERA5 reanalysis archive (no API key).

Annual rainfall drives erosion/landslide/drainage considerations; winter
temperatures drive frost-penetration depth (a founding-depth control).
"""
from __future__ import annotations

import math
from datetime import date
from typing import Optional

import httpx

from ..schemas import Climate

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"


def frost_depth_from_fdd(fdd: float) -> float:
    """Simplified modified-Berggren frost penetration (m) from freezing
    degree-days (deg C-days). Indicative screening value."""
    if fdd <= 0:
        return 0.0
    return round(min(0.045 * math.sqrt(fdd), 3.0), 2)


def wetness(precip_mm: Optional[float]) -> Optional[str]:
    if precip_mm is None:
        return None
    if precip_mm < 250:
        return "Arid"
    if precip_mm < 600:
        return "Semi-arid"
    if precip_mm < 1200:
        return "Moderate"
    if precip_mm < 2000:
        return "Wet"
    return "Very wet"


NORMALS_YEARS = 5  # average the last N full calendar years for a stable normal


def _last_full_year() -> int:
    # ERA5 archive lags a few days; the previous full calendar year is safe.
    return date.today().year - 1


async def fetch_climate(client: httpx.AsyncClient, lat: float, lon: float) -> Climate:
    end_yr = _last_full_year()
    start_yr = end_yr - (NORMALS_YEARS - 1)
    r = await client.get(
        ARCHIVE,
        params={
            "latitude": lat, "longitude": lon,
            "start_date": f"{start_yr}-01-01", "end_date": f"{end_yr}-12-31",
            "daily": "precipitation_sum,temperature_2m_min,temperature_2m_mean,temperature_2m_max",
            "timezone": "auto",
        },
    )
    r.raise_for_status()
    daily = r.json().get("daily", {})
    precip = [v for v in daily.get("precipitation_sum", []) if v is not None]
    tmin = [v for v in daily.get("temperature_2m_min", []) if v is not None]
    tmean = [v for v in daily.get("temperature_2m_mean", []) if v is not None]
    tmax = [v for v in daily.get("temperature_2m_max", []) if v is not None]

    n = NORMALS_YEARS
    annual_precip = round(sum(precip) / n, 0) if precip else None      # mean annual
    min_t = round(min(tmin), 1) if tmin else None                     # coldest observed
    mean_t = round(sum(tmean) / len(tmean), 1) if tmean else None
    max_t = round(max(tmax), 1) if tmax else None
    fdd = round(sum(-t for t in tmean if t < 0) / n, 0) if tmean else 0.0  # mean annual FDD

    # Degree-days (base 18 C), mean annual.
    hdd = round(sum(max(18.0 - t, 0.0) for t in tmean) / n, 0) if tmean else None
    cdd = round(sum(max(t - 18.0, 0.0) for t in tmean) / n, 0) if tmean else None
    # Design temperatures: ~99% winter (1st pct of daily min), ~1% summer (99th pct of daily max).
    heating_design = round(_percentile(tmin, 1), 1) if tmin else None
    cooling_design = round(_percentile(tmax, 99), 1) if tmax else None

    return Climate(
        year=end_yr,
        years_averaged=n,
        annual_precip_mm=annual_precip,
        min_temp_c=min_t,
        mean_temp_c=mean_t,
        max_temp_c=max_t,
        freezing_degree_days=fdd,
        frost_depth_m=frost_depth_from_fdd(fdd),
        wetness_class=wetness(annual_precip),
        hdd18=hdd,
        cdd18=cdd,
        heating_design_temp_c=heating_design,
        cooling_design_temp_c=cooling_design,
        source=f"Open-Meteo ERA5 reanalysis ({start_yr}-{end_yr} normals)",
    )


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)
