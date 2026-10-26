"""Representative sample data for offline / demo mode.

Used when live API calls are unavailable (e.g. no outbound network). Values are
plausible, location-varying placeholders — clearly flagged in the report as
sample data, never presented as a real measurement.
"""
from __future__ import annotations

import math

from datetime import date

from ..schemas import (Climate, Location, SeismicContext, SoilLayer, SoilProfile, Terrain)
from ..engineering.classification import usda_texture, usda_to_uscs

DEPTHS = [("0-5cm", 0, 5), ("5-15cm", 5, 15), ("15-30cm", 15, 30),
          ("30-60cm", 30, 60), ("60-100cm", 60, 100), ("100-200cm", 100, 200)]


def _pseudo(lat: float, lon: float) -> float:
    """Deterministic 0..1 value that varies with position."""
    v = math.sin(lat * 12.9898 + lon * 78.233) * 43758.5453
    return v - math.floor(v)


def demo_location(lat: float, lon: float) -> Location:
    return Location(lat=lat, lon=lon,
                    display_name=f"Sample site @ {lat:.4f}, {lon:.4f}",
                    country="(demo)")


def demo_terrain(lat: float, lon: float) -> Terrain:
    base = 50 + _pseudo(lat, lon) * 600
    slope = round(_pseudo(lon, lat) * 22, 2)
    from .terrain import _classify_terrain
    return Terrain(
        elevation_m=round(base, 1),
        slope_deg=slope,
        aspect_deg=round(_pseudo(lat + 1, lon) * 360, 1),
        relief_m=round(_pseudo(lat, lon + 1) * 15 + slope, 2),
        terrain_class=_classify_terrain(slope),
        source="DEMO (sample data — not a real DEM reading)",
        note="Offline demo mode.",
    )


def demo_soil(lat: float, lon: float) -> SoilProfile:
    # Build a varying clay fraction that generally increases with depth.
    clay0 = 10 + _pseudo(lat, lon) * 45
    profile = SoilProfile(source="DEMO (sample data — not a real SoilGrids query)",
                          note="Offline demo mode.")
    for idx, (label, top, bottom) in enumerate(DEPTHS):
        clay = min(clay0 + idx * 4, 70)
        sand = max(60 - clay * 0.7 - idx * 2, 5)
        silt = max(100 - clay - sand, 0)
        tex = usda_texture(sand, silt, clay)
        profile.layers.append(SoilLayer(
            depth_label=label, top_cm=top, bottom_cm=bottom,
            clay_pct=round(clay, 1), sand_pct=round(sand, 1), silt_pct=round(silt, 1),
            coarse_fragments_pct=round(_pseudo(lat, lon + idx) * 12, 1),
            bulk_density_kg_m3=round(1300 + _pseudo(lon, lat + idx) * 400, 0),
            organic_carbon_pct=round(max(2.0 - idx * 0.3, 0.1), 2),
            ph=round(6.0 + _pseudo(lat + idx, lon) * 2, 1),
            usda_texture=tex, uscs_group=usda_to_uscs(tex)))
    from .soil import _summarise
    _summarise(profile)
    return profile


def demo_climate(lat: float, lon: float) -> Climate:
    from .climate import frost_depth_from_fdd, wetness
    # Rainfall loosely higher near the equator; cold increases with |lat|.
    wet = _pseudo(lat + 3, lon)
    precip = round(100 + wet * 2200 * max(0.2, math.cos(math.radians(lat))), 0)
    mean_t = round(27 - abs(lat) * 0.55 + (_pseudo(lon, lat) - 0.5) * 6, 1)
    min_t = round(mean_t - 8 - abs(lat) * 0.25, 1)
    fdd = round(max(0.0, -min_t) * 25, 0) if min_t < 0 else 0.0
    return Climate(
        year=date.today().year - 1,
        annual_precip_mm=precip, min_temp_c=min_t, mean_temp_c=mean_t,
        freezing_degree_days=fdd, frost_depth_m=frost_depth_from_fdd(fdd),
        wetness_class=wetness(precip),
        source="DEMO (sample data — not a real climate query)", note="Offline demo mode.")


def demo_seismic(lat: float, lon: float) -> SeismicContext:
    from .seismic import _hazard_from, _pga_proxy, SEARCH_RADIUS_KM
    activity = _pseudo(lon, lat)
    count = int(activity * 60)
    max_mag = round(4.0 + activity * 3.2, 1) if count else None
    nearest = round(20 + (1 - activity) * 250, 1) if count else None
    return SeismicContext(
        search_radius_km=SEARCH_RADIUS_KM,
        event_count=count,
        max_magnitude=max_mag,
        nearest_significant_km=nearest,
        largest_event_desc="Sample event (demo)" if count else None,
        hazard_level=_hazard_from(max_mag, count, nearest),
        estimated_pga_g=_pga_proxy(max_mag, nearest),
        source="DEMO (sample data — not a real USGS query)",
        note="Offline demo mode.",
    )
