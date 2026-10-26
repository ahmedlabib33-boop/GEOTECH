"""Screening-level wind & snow load study from real ERA5 climate extremes.

Design wind and snow loads are derived from a Gumbel (Type-I extreme-value) fit
to the ANNUAL MAXIMA of the Open-Meteo ERA5 reanalysis record:

 * Wind: annual-maximum 10 m gust -> T-year gust -> basic velocity pressure
   q = 0.5 * rho * V^2 (rho = 1.25 kg/m3).
 * Snow: annual-maximum on-ground snow depth -> T-year depth -> ground snow
   load from a settled-snowpack density, then a flat-roof snow load.

These are preliminary screening values for early planning. Final wind and snow
loads for design must follow the governing code (e.g. ASCE 7, EN 1991-1-3 /
-1-4) with site-specific terrain, exposure, topography, shape and importance
factors — this tool supplies neither those factors nor the full pressure
coefficients.
"""
from __future__ import annotations

import math
from typing import Optional

from ..schemas import WindSnowStudy

AIR_DENSITY = 1.25            # kg/m3, standard air density for velocity pressure
SNOWPACK_DENSITY = 300.0      # kg/m3, representative settled seasonal snowpack
G = 9.81                      # m/s2
ROOF_SHAPE_FACTOR = 0.8       # mu1 * Ce * Ct for a flat/low-slope roof (screening)
WALL_PRESSURE_COEFF = 1.3     # indicative combined Cpe+Cpi for a low-rise wall


def gumbel_return_level(annual_maxima: list[float], return_period: int) -> Optional[float]:
    """Type-I (Gumbel) extreme-value estimate of the T-year return level from a
    series of annual maxima, using method-of-moments parameters.

    With fewer than three years the sample is too small to extrapolate, so the
    observed maximum is returned instead (never an invented higher value).
    """
    vals = [v for v in annual_maxima if v is not None]
    if not vals:
        return None
    if len(vals) < 3:
        return max(vals)
    n = len(vals)
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / (n - 1)
    std = math.sqrt(var)
    if std <= 0:
        return mean
    beta = std * math.sqrt(6.0) / math.pi
    mu = mean - 0.5772 * beta
    y = -math.log(-math.log(1.0 - 1.0 / return_period))
    return mu + beta * y


def _snow_zone(ground_load_kpa: Optional[float]) -> Optional[str]:
    if ground_load_kpa is None:
        return None
    if ground_load_kpa < 0.1:
        return "Negligible"
    if ground_load_kpa < 0.75:
        return "Light"
    if ground_load_kpa < 2.0:
        return "Moderate"
    if ground_load_kpa < 4.0:
        return "Heavy"
    return "Very heavy"


def _wind_class(gust_ms: Optional[float]) -> str:
    if gust_ms is None:
        return "-"
    if gust_ms < 20:
        return "Low"
    if gust_ms < 32:
        return "Moderate"
    if gust_ms < 45:
        return "High"
    return "Very high (cyclone/hurricane-prone)"


def build_windsnow(wind_annual_max_gust_ms: Optional[list[float]] = None,
                   snow_annual_max_depth_m: Optional[list[float]] = None,
                   dominant_wind_dir: Optional[str] = None,
                   years: Optional[int] = None,
                   return_period: int = 50) -> Optional[WindSnowStudy]:
    """Build the study from annual-maxima series. Returns None when neither a
    wind nor a snow series is available (real-only: nothing is invented)."""
    wind = [v for v in (wind_annual_max_gust_ms or []) if v is not None]
    snow = [v for v in (snow_annual_max_depth_m or []) if v is not None]
    if not wind and not snow:
        return None

    s = WindSnowStudy(
        years_analyzed=years, return_period_years=return_period,
        dominant_wind_dir=dominant_wind_dir,
        source="Gumbel extreme-value fit to Open-Meteo ERA5 annual maxima",
        assumptions=[
            f"{return_period}-year return period (Gumbel / Type-I, method of moments).",
            f"Basic velocity pressure q = 0.5 x rho x V^2, air density {AIR_DENSITY} kg/m3.",
            f"Ground snow load from settled snowpack density {SNOWPACK_DENSITY:.0f} kg/m3; "
            f"flat-roof load = {ROOF_SHAPE_FACTOR} x ground (screening shape/exposure).",
        ],
    )

    # ---- Wind ----
    if wind:
        s.mean_annual_max_gust_ms = round(sum(wind) / len(wind), 1)
        v50 = gumbel_return_level(wind, return_period)
        if v50 is not None:
            v50 = max(v50, max(wind))           # never report below the observed max
            s.design_gust_ms = round(v50, 1)
            s.design_gust_kmh = round(v50 * 3.6, 0)
            q = 0.5 * AIR_DENSITY * v50 ** 2 / 1000.0      # kPa
            s.basic_velocity_pressure_kpa = round(q, 2)
            s.indicative_wall_pressure_kpa = round(q * WALL_PRESSURE_COEFF, 2)
            s.wind_class = _wind_class(v50)
    else:
        s.notes.append("Wind data unavailable — design wind not derived.")

    # ---- Snow ----
    if snow:
        peak = max(snow)
        s.max_observed_snow_depth_m = round(peak, 2)
        if peak < 0.02:
            s.snow_zone = "Negligible"
            s.ground_snow_load_kpa = 0.0
            s.roof_snow_load_kpa = 0.0
            s.notes.append("Essentially snow-free over the ERA5 record — no ground snow load.")
        else:
            d50 = gumbel_return_level(snow, return_period)
            if d50 is not None:
                d50 = max(d50, peak)
                s.design_snow_depth_m = round(d50, 2)
                sk = d50 * SNOWPACK_DENSITY * G / 1000.0   # kPa
                s.ground_snow_load_kpa = round(sk, 2)
                s.roof_snow_load_kpa = round(ROOF_SHAPE_FACTOR * sk, 2)
                s.snow_zone = _snow_zone(s.ground_snow_load_kpa)
    else:
        s.notes.append("Snow data unavailable — ground snow load not derived.")

    return s
