"""Deterministic sample data — TEST FIXTURES ONLY (not part of the product).

These builders let the offline test suite exercise the full pipeline without
network. The application itself contains no demo/sample-data path.
"""
from __future__ import annotations

import math
from datetime import date

from backend.schemas import (Climate, GroundMotion, Hydrology, Location,
                             SeismicContext, SoilLayer, SoilProfile, Terrain,
                             Vegetation, WindSnowStudy)
from backend.engineering.classification import usda_texture, usda_to_uscs

DEPTHS = [("0-5cm", 0, 5), ("5-15cm", 5, 15), ("15-30cm", 15, 30),
          ("30-60cm", 30, 60), ("60-100cm", 60, 100), ("100-200cm", 100, 200)]


def _pseudo(lat: float, lon: float) -> float:
    v = math.sin(lat * 12.9898 + lon * 78.233) * 43758.5453
    return v - math.floor(v)


def fake_location(lat: float, lon: float) -> Location:
    return Location(lat=lat, lon=lon, display_name=f"Test site @ {lat:.4f}, {lon:.4f}",
                    country="(test)")


def fake_terrain(lat: float, lon: float) -> Terrain:
    from backend.services.terrain import _classify_terrain
    base = 50 + _pseudo(lat, lon) * 600
    slope = round(_pseudo(lon, lat) * 22, 2)
    return Terrain(elevation_m=round(base, 1), slope_deg=slope,
                   aspect_deg=round(_pseudo(lat + 1, lon) * 360, 1),
                   relief_m=round(_pseudo(lat, lon + 1) * 15 + slope, 2),
                   terrain_class=_classify_terrain(slope), source="TEST DEM")


def fake_soil(lat: float, lon: float) -> SoilProfile:
    from backend.services.soil import _summarise, _assign_confidence
    clay0 = 10 + _pseudo(lat, lon) * 45
    profile = SoilProfile(source="TEST SoilGrids")
    for idx, (label, top, bottom) in enumerate(DEPTHS):
        clay = min(clay0 + idx * 4, 70)
        sand = max(60 - clay * 0.7 - idx * 2, 5)
        silt = max(100 - clay - sand, 0)
        tex = usda_texture(sand, silt, clay)
        profile.layers.append(SoilLayer(
            depth_label=label, top_cm=top, bottom_cm=bottom, clay_pct=round(clay, 1),
            clay_low_pct=round(max(clay - 8, 0), 1), clay_high_pct=round(clay + 8, 1),
            sand_pct=round(sand, 1), silt_pct=round(silt, 1),
            coarse_fragments_pct=round(_pseudo(lat, lon + idx) * 12, 1),
            bulk_density_kg_m3=round(1300 + _pseudo(lon, lat + idx) * 400, 0),
            organic_carbon_pct=round(max(2.0 - idx * 0.3, 0.1), 2),
            ph=round(6.0 + _pseudo(lat + idx, lon) * 2, 1),
            usda_texture=tex, uscs_group=usda_to_uscs(tex)))
    _summarise(profile)
    _assign_confidence(profile)
    return profile


def fake_climate(lat: float, lon: float) -> Climate:
    from backend.services.climate import frost_depth_from_fdd, wetness
    wet = _pseudo(lat + 3, lon)
    precip = round(100 + wet * 2200 * max(0.2, math.cos(math.radians(lat))), 0)
    mean_t = round(27 - abs(lat) * 0.55 + (_pseudo(lon, lat) - 0.5) * 6, 1)
    min_t = round(mean_t - 8 - abs(lat) * 0.25, 1)
    fdd = round(max(0.0, -min_t) * 25, 0) if min_t < 0 else 0.0
    hdd = round(max(0.0, (18 - mean_t)) * 300, 0)
    cdd = round(max(0.0, (mean_t - 18)) * 200, 0)
    return Climate(year=date.today().year - 1, years_averaged=5, annual_precip_mm=precip,
                   min_temp_c=min_t, mean_temp_c=mean_t, max_temp_c=round(mean_t + 10, 1),
                   freezing_degree_days=fdd, frost_depth_m=frost_depth_from_fdd(fdd),
                   wetness_class=wetness(precip), hdd18=hdd, cdd18=cdd,
                   heating_design_temp_c=round(min_t - 2, 1),
                   cooling_design_temp_c=round(mean_t + 12, 1), source="TEST ERA5")


def fake_vegetation(lat: float, lon: float) -> Vegetation:
    from backend.services.vegetation import cover_class
    base = _pseudo(lat + 5, lon - 2)
    ndvi = round(max(0.02, min(0.9, base * max(0.1, math.cos(math.radians(lat))) + 0.05)), 3)
    cls, desc = cover_class(ndvi)
    return Vegetation(ndvi=ndvi, observation_date=f"{date.today().year - 1}-07-12",
                      cover_class=cls, ground_description=desc, source="TEST MODIS")


def fake_hydrology(lat: float, lon: float) -> Hydrology:
    d = round(50 + _pseudo(lon + 7, lat) * 4000, 0)
    off = d / 111_320.0
    types = ["river", "stream", "lake / pond / reservoir", "coastline / sea", "canal"]
    t = types[int(_pseudo(lat, lon + 9) * len(types)) % len(types)]
    return Hydrology(nearest_water_m=d, nearest_water_type=t,
                     nearest_water_lat=round(lat + off, 6), nearest_water_lon=round(lon + off * 0.6, 6),
                     river_discharge_m3s=round(_pseudo(lon, lat + 4) ** 2 * 1500, 1),
                     source="TEST hydrology")


def fake_windsnow(lat: float, lon: float) -> WindSnowStudy:
    from backend.engineering.windsnow import build_windsnow
    base = _pseudo(lat, lon + 2)
    gusts = [round(22 + base * 18 + (i % 5) * 0.8, 1) for i in range(15)]  # annual max gusts
    coldness = max(0.0, (abs(lat) - 30.0) / 60.0)  # snow only at higher latitudes
    depths = [round(max(0.0, coldness * (0.3 + _pseudo(lat + i, lon))), 2) for i in range(15)]
    study = build_windsnow(wind_annual_max_gust_ms=gusts, snow_annual_max_depth_m=depths,
                           dominant_wind_dir="SW", years=15)
    study.source = "TEST ERA5 extremes"
    return study


def fake_seismic(lat: float, lon: float) -> SeismicContext:
    from backend.services.seismic import _hazard_from, _pga_proxy, SEARCH_RADIUS_KM
    activity = _pseudo(lon, lat)
    count = int(activity * 60)
    max_mag = round(4.0 + activity * 3.2, 1) if count else None
    nearest = round(20 + (1 - activity) * 250, 1) if count else None
    return SeismicContext(search_radius_km=SEARCH_RADIUS_KM, event_count=count,
                          max_magnitude=max_mag, nearest_significant_km=nearest,
                          hazard_level=_hazard_from(max_mag, count, nearest),
                          estimated_pga_g=_pga_proxy(max_mag, nearest), source="TEST USGS")
