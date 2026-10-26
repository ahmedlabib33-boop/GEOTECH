"""Orchestrator: gather remote-sensing data and build a full Assessment.

Live mode fetches the three data domains (terrain, soil, seismic) concurrently.
If any source fails it is recorded as a warning and that domain is reported as
"unavailable" — it is NEVER replaced with synthetic data (real-only).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from .schemas import (AssessRequest, Assessment, Climate, GeotechParameters,
                      HazardRating, Hydrology, Location, SeismicContext,
                      SiteLogistics, SoilProfile, Terrain, Vegetation, WindSnowStudy)
from .services.http import new_client, with_retry
from .services import (geocoding, terrain as terrain_svc, soil as soil_svc,
                       seismic as seismic_svc, climate as climate_svc,
                       vegetation as veg_svc, hydrology as hydro_svc,
                       sentinelhub as sh_svc, groundmotion as gm_svc,
                       windsnow as windsnow_svc, logistics as logistics_svc)
from .engineering.parameters import build_parameters
from .engineering.borehole import build_parameters_from_borehole, has_usable_data
from .engineering.hazards import all_hazards
from .engineering.recommendations import build_recommendations
from .engineering.suitability import build_suitability
from .engineering.hvac import build_hvac
from .engineering.utilities import build_underground
from .engineering.seismic_design import build_seismic_design
from .engineering.country import build_country_context
from .engineering.construction_climate import build_construction_climate
from .engineering.bid import build_bid_risk
from . import llm

DISCLAIMER = (
    "This is an automated PRELIMINARY desk study derived from open remote-sensing "
    "and global geospatial datasets. It uses surface and modelled data only and "
    "contains NO subsurface investigation. Soil parameters and bearing capacities "
    "are indicative screening estimates, not design values. It does not replace a "
    "site-specific geotechnical investigation by a qualified engineer and must not "
    "be used for final design or construction."
)


async def _resolve_location(req: AssessRequest) -> Location:
    if req.lat is not None and req.lon is not None:
        async with new_client() as client:
            return await geocoding.reverse(client, req.lat, req.lon)
    if req.place:
        async with new_client() as client:
            loc = await geocoding.geocode(client, req.place)
            if loc is None:
                raise ValueError(f"Could not geocode place: {req.place!r}")
            return loc
    raise ValueError("Provide either lat/lon or a place name.")


async def _hydro_then_logistics(client, lat: float, lon: float):
    """Hydrology and logistics both hit the public OSM Overpass API; running
    them concurrently from one IP makes the instance reject both. Run them
    sequentially (each catching its own error) so neither starves the other."""
    try:
        hydro = await with_retry(lambda: hydro_svc.fetch_hydrology(client, lat, lon))
    except Exception as e:
        hydro = e
    try:
        logi = await with_retry(lambda: logistics_svc.fetch_logistics(client, lat, lon),
                                attempts=1)
    except Exception as e:
        logi = e
    return hydro, logi


async def _gather_live(lat: float, lon: float):
    """Fetch terrain, soil, seismic etc. concurrently, each with retry; tolerate
    partial failure (a source that still fails degrades to sample data)."""
    async with new_client() as client:
        results = await asyncio.gather(
            with_retry(lambda: terrain_svc.fetch_terrain(client, lat, lon)),
            # Soil uses a long dedicated timeout; a single attempt keeps the
            # whole gather within the 60 s function budget.
            with_retry(lambda: soil_svc.fetch_soil(client, lat, lon), attempts=1),
            with_retry(lambda: seismic_svc.fetch_seismic(client, lat, lon)),
            with_retry(lambda: climate_svc.fetch_climate(client, lat, lon)),
            with_retry(lambda: veg_svc.fetch_vegetation(client, lat, lon)),
            # Hydrology + logistics share Overpass, so they run one after the other.
            _hydro_then_logistics(client, lat, lon),
            # Wind/snow pulls a long hourly snow series; one attempt keeps the
            # whole gather within the 60 s function budget (like soil).
            with_retry(lambda: windsnow_svc.fetch_windsnow(client, lat, lon), attempts=1),
            return_exceptions=True,
        )
    return results


async def run_assessment(req: AssessRequest, ai_commentary: bool = False) -> Assessment:
    warnings: list[str] = []
    location = await _resolve_location(req)
    lat, lon = location.lat, location.lon

    data_mode = "live"
    if True:
        (t_res, s_res, q_res, c_res, v_res, hl_res, ws_res), sentinel, ground_motion = \
            await asyncio.gather(
                _gather_live(lat, lon),
                sh_svc.fetch_sentinel(lat, lon),
                gm_svc.fetch_ground_motion(lat, lon, req.insar_velocity_mm_yr))
        # _hydro_then_logistics returns a (hydrology, logistics) pair; if the
        # whole coroutine itself errored, treat both as failed.
        if isinstance(hl_res, tuple):
            h_res, lo_res = hl_res
        else:
            h_res = lo_res = hl_res

        # REAL-ONLY: a failed/unavailable source is reported as unavailable and
        # is NEVER replaced with synthetic sample data.
        if isinstance(t_res, Terrain):
            terrain = t_res
        else:
            terrain = Terrain(source="unavailable", note="Terrain/DEM data unavailable at this point.")
            warnings.append("Terrain/DEM source unavailable — not substituted (real-only).")

        if isinstance(s_res, SoilProfile) and s_res.layers:
            soil = s_res
        else:
            soil = SoilProfile(source="unavailable", note="Soil data unavailable at this point.")
            warnings.append("Soil (SoilGrids) unavailable — not substituted (real-only).")

        if isinstance(q_res, SeismicContext):
            seismic = q_res
        else:
            seismic = SeismicContext(search_radius_km=300.0, source="unavailable",
                                     note="Seismic catalogue unavailable.")
            warnings.append("Seismic (USGS) source unavailable — not substituted (real-only).")

        if isinstance(c_res, Climate) and c_res.annual_precip_mm is not None:
            climate = c_res
        else:
            climate = Climate(source="unavailable", note="Climate data unavailable.")
            warnings.append("Climate (ERA5) source unavailable — not substituted (real-only).")

        if isinstance(v_res, Vegetation) and v_res.ndvi is not None:
            vegetation = v_res
        else:
            vegetation = Vegetation(source="unavailable", note="Vegetation/NDVI data unavailable.")
            warnings.append("Vegetation/NDVI source unavailable — not substituted (real-only).")

        if isinstance(h_res, Hydrology):
            hydrology = h_res
            if hydrology.height_above_water_m is None:
                hydrology.height_above_water_m = terrain.elevation_m
        else:
            hydrology = Hydrology(source="unavailable", note="Hydrology data unavailable.")
            warnings.append("Hydrology source unavailable — not substituted (real-only).")

        # Wind/snow extremes (ERA5 Gumbel). Real-only: used only when the fetch
        # succeeded and produced at least one real design value.
        if (isinstance(ws_res, WindSnowStudy) and (ws_res.source or "") != "unavailable"
                and (ws_res.design_gust_ms is not None or ws_res.snow_zone is not None)):
            wind_snow = ws_res
        else:
            wind_snow = None
            warnings.append("Wind/snow (ERA5 extremes) unavailable — not substituted (real-only).")

        # Site logistics / access (OSM). Degrades gracefully to a note.
        if isinstance(lo_res, SiteLogistics):
            logistics = lo_res
        else:
            logistics = None
            warnings.append("Logistics (OSM Overpass) unavailable — not substituted (real-only).")

        # Upgrade NDVI to the Sentinel-2 10 m reading when available (real data).
        if sentinel is not None and sentinel.ndvi is not None:
            from .services.vegetation import cover_class
            cls, desc = cover_class(sentinel.ndvi)
            vegetation.ndvi = sentinel.ndvi
            vegetation.cover_class = cls
            vegetation.ground_description = desc
            vegetation.observation_date = sentinel.observation_date or vegetation.observation_date
            vegetation.source = "Sentinel-2 L2A 10 m (Sentinel Hub)"

    # Availability of real data (drives real-only gating).
    terrain_ok = terrain.elevation_m is not None or terrain.slope_deg is not None
    # Soil is usable only if at least one layer has a real classified texture.
    # SoilGrids can return a 200 with all-null values (urban/rock/nodata pixel);
    # that is NOT usable and must not fall back to generic default parameters.
    soil_ok = any(l.usda_texture for l in soil.layers)
    if soil.layers and not soil_ok and "unavailable" not in (soil.source or ""):
        warnings.append("Soil (SoilGrids) has no data at this exact point "
                        "(urban/rock/nodata pixel) — not substituted (real-only).")
        soil.note = "SoilGrids returned no soil values at this point."
    seismic_ok = (seismic.source or "") != "unavailable"

    gw_depth = None
    if has_usable_data(req.borehole):
        params = build_parameters_from_borehole(
            req.borehole, req.foundation_width_m, req.foundation_depth_m)
        gw_depth = req.borehole.groundwater_depth_m
        warnings.append(
            "Foundation parameters derived from the supplied BOREHOLE (measured data).")
    elif soil_ok:
        params = build_parameters(soil, terrain, climate,
                                  req.foundation_width_m, req.foundation_depth_m,
                                  req.foundation_length_m)
    else:
        params = GeotechParameters(
            data_basis="unavailable",
            soil_description="Not computed — no real soil data for this point.",
            recommended_foundation="Intrusive ground investigation required (no soil data).")

    hazards = all_hazards(terrain, soil, seismic, climate, vegetation, hydrology,
                          gw_depth, ground_motion)

    # REAL-ONLY: mark hazards whose required real inputs are missing as
    # "Insufficient data" instead of assessing from assumed defaults.
    if data_mode == "live":
        req_ok = {
            "Flooding / inundation": terrain_ok,
            "Slope instability / landslide": terrain_ok,
            "Seismicity": seismic_ok,
            "Expansive / shrink-swell soil": soil_ok,
            "Liquefaction potential": soil_ok and seismic_ok,
        }
        hazards = [h if req_ok.get(h.name, True) else
                   HazardRating(name=h.name, level="Insufficient data", score=0.0,
                                rationale="Required input data was unavailable; not "
                                          "assessed (real-only mode).")
                   for h in hazards]

    suitability = build_suitability(hazards, params, terrain)
    recommendations = build_recommendations(terrain, soil, seismic, params, hazards,
                                            climate, vegetation, hydrology)
    hvac = build_hvac(climate, req.building_floor_area_m2, req.building_type)
    underground = build_underground(soil, climate, hydrology, terrain, gw_depth)
    seismic_design = build_seismic_design(
        seismic if seismic_ok else None, params.vs30_proxy_mps, req.design_pga_g)
    # Overseas-bidding layer
    country_context = build_country_context(location)
    construction_climate = build_construction_climate(climate)
    bid_risk = build_bid_risk(hazards, params, logistics, construction_climate,
                              country_context)

    assessment = Assessment(
        project_name=req.project_name or "Untitled Site",
        generated_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        location=location,
        terrain=terrain,
        soil=soil,
        seismic=seismic,
        climate=climate,
        vegetation=vegetation,
        sentinel=sentinel,
        hydrology=hydrology,
        ground_motion=ground_motion,
        borehole=req.borehole if has_usable_data(req.borehole) else None,
        parameters=params,
        suitability=suitability,
        hvac=hvac,
        underground=underground,
        wind_snow=wind_snow,
        seismic_design=seismic_design,
        country_context=country_context,
        logistics=logistics,
        construction_climate=construction_climate,
        bid_risk=bid_risk,
        hazards=hazards,
        recommendations=recommendations,
        data_mode=data_mode,
        warnings=warnings,
        disclaimer=DISCLAIMER,
    )

    if ai_commentary:
        text, model = await asyncio.to_thread(llm.generate_commentary, assessment)
        if text:
            assessment.commentary = text
            assessment.commentary_model = model
        else:
            assessment.warnings.append(
                "AI commentary unavailable (no ANTHROPIC_API_KEY set or model error).")

    return assessment
