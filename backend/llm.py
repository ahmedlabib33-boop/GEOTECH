"""Optional LLM-generated engineering commentary.

The model is used ONLY to interpret the numbers already computed from real data
— it is explicitly forbidden from inventing any value. It activates only when an
ANTHROPIC_API_KEY is configured; otherwise commentary is skipped and the rest of
the report is unaffected.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from .schemas import Assessment

DEFAULT_MODEL = os.environ.get("GEOTECH_LLM_MODEL", "claude-3-5-sonnet-latest")

SYSTEM = (
    "You are a chartered geotechnical engineer writing the 'Engineering Commentary' "
    "paragraph of a PRELIMINARY satellite/remote-sensing desk study. You are given a "
    "JSON assessment that was computed from open geospatial data.\n\n"
    "STRICT RULES:\n"
    "1. Use ONLY numbers and facts present in the JSON. NEVER invent or estimate any "
    "value (no made-up bearing capacities, SPT, depths, costs, coordinates, etc.).\n"
    "2. If something is not in the JSON, do not state it. You may note what is unknown.\n"
    "3. Interpret and connect the provided findings (soil, terrain, hazards, climate, "
    "hydrology, suitability) into a concise professional narrative and the main "
    "engineering implications.\n"
    "4. Emphasise uncertainty: these are screening estimates from surface/modelled data "
    "with no subsurface investigation.\n"
    "5. 150-220 words, plain prose (no headings/markdown). End by deferring to an "
    "intrusive ground investigation.\n"
    "6. Do not give a professional guarantee or sign-off."
)


def _compact(a: Assessment) -> dict:
    """A trimmed, number-focused view of the assessment for grounding."""
    return {
        "location": a.location.model_dump(),
        "terrain": a.terrain.model_dump(include={
            "elevation_m", "slope_deg", "terrain_class"}),
        "soil": {
            "dominant_usda_texture": a.soil.dominant_usda_texture,
            "dominant_uscs_group": a.soil.dominant_uscs_group,
            "texture_confidence": a.soil.texture_confidence,
            "topsoil_clay_pct": a.soil.layers[0].clay_pct if a.soil.layers else None,
        },
        "parameters": a.parameters.model_dump(exclude={"bearing_curve"}),
        "climate": a.climate.model_dump(include={
            "annual_precip_mm", "wetness_class", "frost_depth_m", "min_temp_c"}),
        "vegetation": a.vegetation.model_dump(include={"ndvi", "cover_class"}),
        "hydrology": a.hydrology.model_dump(include={
            "nearest_water_m", "nearest_water_type", "river_discharge_m3s"}),
        "hazards": [h.model_dump(include={"name", "level"}) for h in a.hazards],
        "suitability": a.suitability.model_dump() if a.suitability else None,
        "data_mode": a.data_mode,
    }


def generate_commentary(a: Assessment) -> tuple[Optional[str], Optional[str]]:
    """Return (commentary_text, model_id) or (None, None) if unavailable."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None, None
    try:
        from anthropic import Anthropic
    except Exception:
        return None, None

    try:
        client = Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=600,
            system=SYSTEM,
            messages=[{"role": "user", "content":
                       "Assessment JSON:\n" + json.dumps(_compact(a), default=str)}],
        )
        parts = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
        text = "\n".join(parts).strip()
        return (text or None), DEFAULT_MODEL
    except Exception:
        # Never let the LLM break the core report.
        return None, None
