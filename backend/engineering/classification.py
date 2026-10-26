"""Soil classification + typical geotechnical parameters.

`usda_texture` implements the standard USDA textural-triangle algorithm from
sand/silt/clay percentages. `SOIL_PARAMS` maps each texture to an approximate
USCS group and *typical* preliminary design parameters drawn from standard
geotechnical references (e.g. Bowles, Terzaghi & Peck ranges). These are
desk-study estimates for screening only — never a substitute for lab testing.
"""
from __future__ import annotations

from typing import Optional


def usda_texture(sand: Optional[float], silt: Optional[float],
                 clay: Optional[float]) -> Optional[str]:
    """Classify into one of the 12 USDA texture classes."""
    if sand is None or silt is None or clay is None:
        return None
    # Normalise to 100 % in case of rounding / coarse-fragment effects.
    total = sand + silt + clay
    if total <= 0:
        return None
    sand = sand * 100.0 / total
    silt = silt * 100.0 / total
    clay = clay * 100.0 / total

    if silt + 1.5 * clay < 15:
        return "Sand"
    if silt + 1.5 * clay >= 15 and silt + 2 * clay < 30:
        return "Loamy sand"
    if (7 <= clay < 20 and sand > 52 and silt + 2 * clay >= 30) or (clay < 7 and silt < 50 and silt + 2 * clay >= 30):
        return "Sandy loam"
    if 7 <= clay < 27 and 28 <= silt < 50 and sand <= 52:
        return "Loam"
    if (silt >= 50 and 12 <= clay < 27) or (50 <= silt < 80 and clay < 12):
        return "Silt loam"
    if silt >= 80 and clay < 12:
        return "Silt"
    if 20 <= clay < 35 and silt < 28 and sand > 45:
        return "Sandy clay loam"
    if 27 <= clay < 40 and 20 < sand <= 45:
        return "Clay loam"
    if 27 <= clay < 40 and sand <= 20:
        return "Silty clay loam"
    if clay >= 35 and sand > 45:
        return "Sandy clay"
    if clay >= 40 and silt >= 40:
        return "Silty clay"
    if clay >= 40 and sand <= 45 and silt < 40:
        return "Clay"
    return "Loam"


# Typical preliminary parameters per USDA texture.
#   uscs            : approximate Unified Soil Classification group
#   phi             : effective friction angle (deg)
#   cohesion        : effective/undrained cohesion proxy (kPa)
#   gamma           : moist unit weight (kN/m3)
#   spt_n           : typical SPT N range (descriptive)
#   bearing_kpa     : typical presumed allowable bearing pressure range (kPa)
#   settlement      : qualitative settlement sensitivity
#   description     : short engineering description
SOIL_PARAMS: dict[str, dict] = {
    "Sand":             {"uscs": "SP", "phi": 33, "cohesion": 0,  "gamma": 18.0, "spt_n": "10-30 (medium dense)", "bearing": (150, 300), "settlement": "Low (granular, immediate)", "description": "Poorly graded sand"},
    "Loamy sand":       {"uscs": "SM", "phi": 31, "cohesion": 2,  "gamma": 18.0, "spt_n": "8-25",                 "bearing": (120, 250), "settlement": "Low to moderate",             "description": "Silty sand"},
    "Sandy loam":       {"uscs": "SM", "phi": 30, "cohesion": 5,  "gamma": 18.5, "spt_n": "8-20",                 "bearing": (100, 220), "settlement": "Moderate",                    "description": "Silty / clayey sand"},
    "Loam":             {"uscs": "CL-ML", "phi": 28, "cohesion": 8, "gamma": 18.5, "spt_n": "6-18",               "bearing": (100, 200), "settlement": "Moderate",                    "description": "Sandy silt / lean mixture"},
    "Silt loam":        {"uscs": "ML", "phi": 27, "cohesion": 8,  "gamma": 18.0, "spt_n": "5-15",                 "bearing": (90, 180),  "settlement": "Moderate",                    "description": "Low-plasticity silt"},
    "Silt":             {"uscs": "ML", "phi": 26, "cohesion": 5,  "gamma": 18.0, "spt_n": "4-12",                 "bearing": (75, 150),  "settlement": "Moderate to high",            "description": "Non-plastic to low-plasticity silt"},
    "Sandy clay loam":  {"uscs": "SC", "phi": 27, "cohesion": 12, "gamma": 19.0, "spt_n": "6-16",                 "bearing": (100, 200), "settlement": "Moderate",                    "description": "Clayey sand"},
    "Clay loam":        {"uscs": "CL", "phi": 24, "cohesion": 18, "gamma": 19.0, "spt_n": "5-15 (firm-stiff)",    "bearing": (100, 190), "settlement": "Moderate",                    "description": "Lean clay"},
    "Silty clay loam":  {"uscs": "CL-ML", "phi": 23, "cohesion": 18, "gamma": 18.5, "spt_n": "4-12",              "bearing": (90, 170),  "settlement": "Moderate to high",            "description": "Silty lean clay"},
    "Sandy clay":       {"uscs": "SC", "phi": 25, "cohesion": 15, "gamma": 19.0, "spt_n": "5-14",                 "bearing": (100, 180), "settlement": "Moderate",                    "description": "Sandy clay"},
    "Silty clay":       {"uscs": "CH", "phi": 20, "cohesion": 25, "gamma": 18.0, "spt_n": "4-12 (firm-stiff)",    "bearing": (75, 150),  "settlement": "High (consolidation)",        "description": "Fat silty clay"},
    "Clay":             {"uscs": "CH", "phi": 18, "cohesion": 30, "gamma": 18.0, "spt_n": "4-15 (firm-stiff)",    "bearing": (75, 150),  "settlement": "High (consolidation / shrink-swell)", "description": "High-plasticity clay"},
}

_DEFAULT = {"uscs": "SM/CL", "phi": 28, "cohesion": 10, "gamma": 18.5,
            "spt_n": "variable", "bearing": (100, 180), "settlement": "Moderate",
            "description": "Mixed soil"}


def usda_to_uscs(texture: Optional[str]) -> Optional[str]:
    if texture is None:
        return None
    return SOIL_PARAMS.get(texture, _DEFAULT)["uscs"]


def params_for(texture: Optional[str]) -> dict:
    if texture is None:
        return dict(_DEFAULT)
    return dict(SOIL_PARAMS.get(texture, _DEFAULT))
