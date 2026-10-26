"""Derive qualitative geohazard ratings from the collected data."""
from __future__ import annotations

import math
from typing import Optional

from ..schemas import (Climate, HazardRating, Hydrology, SeismicContext,
                       SoilProfile, Terrain, Vegetation)


def _level(score: float) -> str:
    if score < 0.25:
        return "Low"
    if score < 0.5:
        return "Moderate"
    if score < 0.75:
        return "High"
    return "Very High"


def _top_clay(soil: SoilProfile) -> Optional[float]:
    for layer in soil.layers:
        if layer.clay_pct is not None:
            return layer.clay_pct
    return None


def landslide_hazard(terrain: Terrain, soil: SoilProfile,
                     climate: Optional[Climate] = None,
                     vegetation: Optional[Vegetation] = None) -> HazardRating:
    slope = terrain.slope_deg or 0.0
    clay = _top_clay(soil) or 0.0
    precip = (climate.annual_precip_mm if climate else None) or 0.0
    ndvi = vegetation.ndvi if vegetation else None
    # Slope dominates; clay-rich soils and high rainfall raise susceptibility.
    rain_factor = min(precip / 2000.0, 1.0)
    score = (min(slope / 35.0, 1.0) * 0.65
             + min(clay / 60.0, 1.0) * 0.20
             + rain_factor * 0.15)
    # Dense vegetation (high NDVI) reinforces slopes -> reduce susceptibility.
    if ndvi is not None:
        score *= (1.0 - 0.20 * max(0.0, min(ndvi, 1.0)))
    rationale = (
        f"Slope {slope:.1f}deg from DEM"
        + (f", clay ~{clay:.0f}% near surface" if clay else "")
        + (f", rainfall ~{precip:.0f} mm/yr" if precip else "")
        + (f", NDVI {ndvi:.2f} (root reinforcement)" if ndvi is not None else "")
        + ". Steep, clay-rich, wet, sparsely vegetated slopes are most unstable."
    )
    return HazardRating(name="Slope instability / landslide", level=_level(score),
                        score=round(min(score, 1.0), 2), rationale=rationale)


def seismic_hazard(seismic: SeismicContext) -> HazardRating:
    mag = seismic.max_magnitude or 0.0
    near = seismic.nearest_significant_km
    count = seismic.event_count
    score = min(mag / 8.0, 1.0) * 0.6 + min(count / 200.0, 1.0) * 0.2
    if near is not None:
        score += (1.0 - min(near / 300.0, 1.0)) * 0.2
    rationale = (
        f"{count} M>=4 events within {seismic.search_radius_km:.0f} km; "
        f"max M{mag:.1f}"
        + (f", nearest {near:.0f} km" if near is not None else "")
        + (f"; indicative PGA ~{seismic.estimated_pga_g}g" if seismic.estimated_pga_g else "")
        + "."
    )
    return HazardRating(name="Seismicity", level=_level(score),
                        score=round(min(score, 1.0), 2), rationale=rationale)


def expansive_soil_hazard(soil: SoilProfile) -> HazardRating:
    clay = _top_clay(soil) or 0.0
    texture = (soil.dominant_usda_texture or "").lower()
    score = min(clay / 60.0, 1.0)
    if "clay" in texture:
        score = min(score + 0.15, 1.0)
    rationale = (
        f"Near-surface clay ~{clay:.0f}% (dominant texture: "
        f"{soil.dominant_usda_texture or 'unknown'}). High-plasticity clays "
        "can shrink/swell with moisture change."
    )
    return HazardRating(name="Expansive / shrink-swell soil", level=_level(score),
                        score=round(score, 2), rationale=rationale)


def liquefaction_hazard(soil: SoilProfile, seismic: SeismicContext,
                        terrain: Terrain, gw_depth_m: Optional[float] = None) -> HazardRating:
    # Screening proxy: loose saturated sands/silts in low-lying, seismic areas.
    texture = (soil.dominant_usda_texture or "").lower()
    sandy = any(k in texture for k in ("sand", "silt", "loamy"))
    low_lying = (terrain.elevation_m is not None and terrain.elevation_m < 20) or \
                ((terrain.slope_deg or 99) < 3)
    seismic_score = min((seismic.max_magnitude or 0) / 8.0, 1.0)
    base = (0.45 if sandy else 0.1) + (0.2 if low_lying else 0.0)
    # Measured shallow groundwater strongly increases liquefaction potential.
    gw_txt = ""
    if gw_depth_m is not None:
        if gw_depth_m <= 3:
            base += 0.25
        elif gw_depth_m <= 6:
            base += 0.12
        gw_txt = f" Measured water table at {gw_depth_m:.1f} m."
    score = min(base * (0.4 + 0.6 * seismic_score), 1.0)
    rationale = (
        f"Soil texture {soil.dominant_usda_texture or 'unknown'}, "
        f"{'low-lying/flat' if low_lying else 'elevated/sloping'} terrain, "
        f"max historical M{seismic.max_magnitude or 0:.1f}.{gw_txt} Loose saturated "
        "granular soils under strong shaking are liquefaction-prone."
    )
    return HazardRating(name="Liquefaction potential", level=_level(score),
                        score=round(score, 2), rationale=rationale)


def flood_hazard(terrain: Terrain, climate: Optional[Climate] = None,
                 hydrology: Optional[Hydrology] = None) -> HazardRating:
    elev = terrain.elevation_m
    slope = terrain.slope_deg if terrain.slope_deg is not None else 99
    precip = (climate.annual_precip_mm if climate else None) or 0.0
    near = hydrology.nearest_water_m if hydrology else None
    discharge = hydrology.river_discharge_m3s if hydrology else None

    score = 0.0
    # Low, flat ground pools water.
    if elev is not None and elev < 10:
        score += 0.30
    elif elev is not None and elev < 30:
        score += 0.15
    if slope < 2:
        score += 0.20
    elif slope < 5:
        score += 0.10
    # Proximity to surface water.
    if near is not None:
        if near < 100:
            score += 0.35
        elif near < 500:
            score += 0.22
        elif near < 2000:
            score += 0.10
    # Riverine flood magnitude (GloFAS discharge) — log-scaled.
    if discharge:
        score += min(math.log10(discharge + 1) / 4.0, 1.0) * 0.20
    # Wet climate.
    score += min(precip / 2500.0, 1.0) * 0.10

    bits = []
    if elev is not None:
        bits.append(f"elevation {elev:.0f} m")
    if near is not None:
        bits.append(f"nearest water ~{near:.0f} m ({hydrology.nearest_water_type})")
    if discharge:
        bits.append(f"river discharge ~{discharge:.0f} m³/s")
    if precip:
        bits.append(f"rainfall ~{precip:.0f} mm/yr")
    rationale = ("; ".join(bits) or "limited hydrological data") + \
        ". Low, flat ground near water with high flow/rainfall floods most readily."
    return HazardRating(name="Flooding / inundation", level=_level(min(score, 1.0)),
                        score=round(min(score, 1.0), 2), rationale=rationale)


def all_hazards(terrain: Terrain, soil: SoilProfile, seismic: SeismicContext,
                climate: Optional[Climate] = None,
                vegetation: Optional[Vegetation] = None,
                hydrology: Optional[Hydrology] = None,
                gw_depth_m: Optional[float] = None) -> list[HazardRating]:
    return [
        flood_hazard(terrain, climate, hydrology),
        landslide_hazard(terrain, soil, climate, vegetation),
        seismic_hazard(seismic),
        expansive_soil_hazard(soil),
        liquefaction_hazard(soil, seismic, terrain, gw_depth_m),
    ]
