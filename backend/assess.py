"""Orchestrator: gather remote-sensing data and build a full Assessment.

Live mode fetches the three data domains (terrain, soil, seismic) concurrently.
If any source fails it is recorded as a warning and the demo fallback fills that
domain so a report can still be produced. Full offline/demo mode bypasses the
network entirely.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from .schemas import (AssessRequest, Assessment, Climate, Hydrology, Location,
                      SeismicContext, SoilProfile, Terrain, Vegetation)
from .services.http import new_client
from .services import (geocoding, terrain as terrain_svc, soil as soil_svc,
                       seismic as seismic_svc, climate as climate_svc,
                       vegetation as veg_svc, hydrology as hydro_svc)
from .services import demo
from .engineering.parameters import build_parameters
from .engineering.borehole import build_parameters_from_borehole, has_usable_data
from .engineering.hazards import all_hazards
from .engineering.recommendations import build_recommendations
from .engineering.suitability import build_suitability
from . import llm

DISCLAIMER = (
    "This is an automated PRELIMINARY desk study derived from open remote-sensing "
    "and global geospatial datasets. It uses surface and modelled data only and "
    "contains NO subsurface investigation. Soil parameters and bearing capacities "
    "are indicative screening estimates, not design values. It does not replace a "
    "site-specific geotechnical investigation by a qualified engineer and must not "
    "be used for final design or construction."
)


async def _resolve_location(req: AssessRequest, demo_mode: bool) -> Location:
    if req.lat is not None and req.lon is not None:
        if demo_mode:
            return demo.demo_location(req.lat, req.lon)
        async with new_client() as client:
            return await geocoding.reverse(client, req.lat, req.lon)
    if req.place:
        if demo_mode:
            # Can't geocode offline; synthesise a deterministic coordinate.
            h = abs(hash(req.place))
            lat = (h % 1400) / 10.0 - 60.0
            lon = (h // 1400 % 3600) / 10.0 - 180.0
            loc = demo.demo_location(lat, lon)
            loc.display_name = f"{req.place} (demo coordinates)"
            return loc
        async with new_client() as client:
            loc = await geocoding.geocode(client, req.place)
            if loc is None:
                raise ValueError(f"Could not geocode place: {req.place!r}")
            return loc
    raise ValueError("Provide either lat/lon or a place name.")


async def _gather_live(lat: float, lon: float):
    """Fetch terrain, soil, seismic concurrently; tolerate partial failure."""
    async with new_client() as client:
        results = await asyncio.gather(
            terrain_svc.fetch_terrain(client, lat, lon),
            soil_svc.fetch_soil(client, lat, lon),
            seismic_svc.fetch_seismic(client, lat, lon),
            climate_svc.fetch_climate(client, lat, lon),
            veg_svc.fetch_vegetation(client, lat, lon),
            hydro_svc.fetch_hydrology(client, lat, lon),
            return_exceptions=True,
        )
    return results


async def run_assessment(req: AssessRequest, demo_mode: bool = False,
                         ai_commentary: bool = False) -> Assessment:
    warnings: list[str] = []
    location = await _resolve_location(req, demo_mode)
    lat, lon = location.lat, location.lon

    if demo_mode:
        terrain = demo.demo_terrain(lat, lon)
        soil = demo.demo_soil(lat, lon)
        seismic = demo.demo_seismic(lat, lon)
        climate = demo.demo_climate(lat, lon)
        vegetation = demo.demo_vegetation(lat, lon)
        hydrology = demo.demo_hydrology(lat, lon, terrain)
        data_mode = "demo"
    else:
        data_mode = "live"
        t_res, s_res, q_res, c_res, v_res, h_res = await _gather_live(lat, lon)

        if isinstance(t_res, Terrain):
            terrain = t_res
        else:
            warnings.append(f"Terrain source failed ({type(t_res).__name__}); using sample data.")
            terrain = demo.demo_terrain(lat, lon)

        if isinstance(s_res, SoilProfile) and s_res.layers:
            soil = s_res
        else:
            reason = type(s_res).__name__ if isinstance(s_res, Exception) else "no coverage"
            warnings.append(f"Soil source unavailable ({reason}); using sample data.")
            soil = demo.demo_soil(lat, lon)

        if isinstance(q_res, SeismicContext):
            seismic = q_res
        else:
            warnings.append(f"Seismic source failed ({type(q_res).__name__}); using sample data.")
            seismic = demo.demo_seismic(lat, lon)

        if isinstance(c_res, Climate) and c_res.annual_precip_mm is not None:
            climate = c_res
        else:
            reason = type(c_res).__name__ if isinstance(c_res, Exception) else "no coverage"
            warnings.append(f"Climate source unavailable ({reason}); using sample data.")
            climate = demo.demo_climate(lat, lon)

        if isinstance(v_res, Vegetation) and v_res.ndvi is not None:
            vegetation = v_res
        else:
            reason = type(v_res).__name__ if isinstance(v_res, Exception) else "no coverage"
            warnings.append(f"Vegetation/NDVI source unavailable ({reason}); using sample data.")
            vegetation = demo.demo_vegetation(lat, lon)

        if isinstance(h_res, Hydrology):
            hydrology = h_res
            if hydrology.height_above_water_m is None:
                hydrology.height_above_water_m = terrain.elevation_m
        else:
            warnings.append(f"Hydrology source failed ({type(h_res).__name__}); using sample data.")
            hydrology = demo.demo_hydrology(lat, lon, terrain)

    gw_depth = None
    if has_usable_data(req.borehole):
        params = build_parameters_from_borehole(
            req.borehole, req.foundation_width_m, req.foundation_depth_m)
        gw_depth = req.borehole.groundwater_depth_m
        warnings.append(
            "Foundation parameters derived from the supplied BOREHOLE (measured data), "
            "overriding the satellite soil estimate.")
    else:
        params = build_parameters(soil, terrain, climate,
                                  req.foundation_width_m, req.foundation_depth_m)

    hazards = all_hazards(terrain, soil, seismic, climate, vegetation, hydrology, gw_depth)
    suitability = build_suitability(hazards, params, terrain)
    recommendations = build_recommendations(terrain, soil, seismic, params, hazards,
                                            climate, vegetation, hydrology)

    assessment = Assessment(
        project_name=req.project_name or "Untitled Site",
        generated_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        location=location,
        terrain=terrain,
        soil=soil,
        seismic=seismic,
        climate=climate,
        vegetation=vegetation,
        hydrology=hydrology,
        borehole=req.borehole if has_usable_data(req.borehole) else None,
        parameters=params,
        suitability=suitability,
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
