"""Screening-level underground-networks / excavation study.

Derived from the real soil, groundwater, frost, rainfall and terrain data for
the site. Covers what the ground conditions imply for buried water/sewer/
drainage/utility networks: infiltration (SuDS), soil corrosivity and pipe
material, frost burial depth, trench support, dewatering, stormwater and
bedding. Screening only — confirm with a ground investigation and the relevant
utility/drainage codes.
"""
from __future__ import annotations

from typing import Optional

from ..schemas import Climate, Hydrology, SoilProfile, Terrain, UndergroundStudy

# Near-surface permeability by USDA texture.
_PERM = {
    "Sand": ("High", "feasible"), "Loamy sand": ("High", "feasible"),
    "Sandy loam": ("Moderate", "likely feasible"), "Loam": ("Moderate", "likely feasible"),
    "Silt loam": ("Low-moderate", "marginal — test infiltration"),
    "Silt": ("Low-moderate", "marginal — test infiltration"),
    "Sandy clay loam": ("Low-moderate", "marginal — test infiltration"),
    "Clay loam": ("Low", "not recommended — use attenuation"),
    "Silty clay loam": ("Low", "not recommended — use attenuation"),
    "Sandy clay": ("Low", "not recommended — use attenuation"),
    "Silty clay": ("Very low", "not recommended — use attenuation/outfall"),
    "Clay": ("Very low", "not recommended — use attenuation/outfall"),
}


def _top_layer(soil: SoilProfile):
    return soil.layers[0] if soil.layers else None


def _corrosivity(soil: SoilProfile) -> tuple[Optional[str], Optional[str]]:
    l = _top_layer(soil)
    if l is None or l.usda_texture is None:
        return None, None
    texture = (soil.dominant_usda_texture or "").lower()
    ph = l.ph
    score = 0
    if "clay" in texture:
        score += 2            # clays hold moisture, lower resistivity
    elif "silt" in texture or "loam" in texture:
        score += 1
    if ph is not None and (ph < 5.5 or ph > 8.5):
        score += 2
    elif ph is not None and (ph < 6.0 or ph > 8.0):
        score += 1
    level = "Low" if score <= 1 else "Moderate" if score <= 3 else "High"
    if level == "High":
        guide = ("Aggressive to buried ferrous metal: prefer plastic (PE/PVC) or "
                 "protect steel/ductile iron with coatings + cathodic protection; "
                 "use sulfate-resistant cement for buried concrete.")
    elif level == "Moderate":
        guide = ("Moderately corrosive: favour plastic pipe; coat/sleeve ferrous "
                 "pipe and check sulfate content for buried concrete.")
    else:
        guide = "Low corrosivity: standard pipe materials generally acceptable."
    return level, guide


def build_underground(soil: SoilProfile, climate: Climate, hydrology: Hydrology,
                      terrain: Terrain, gw_depth_m: Optional[float] = None) -> UndergroundStudy:
    s = UndergroundStudy(source="Derived from site soil, groundwater, frost, "
                                "rainfall & terrain data")
    texture = soil.dominant_usda_texture
    cohesive = bool(texture and "clay" in texture.lower())

    # Infiltration / SuDS
    if texture and texture in _PERM:
        perm, soak = _PERM[texture]
        s.infiltration_class = perm
        s.soakaway_feasibility = soak
    elif texture:
        s.infiltration_class = "Moderate"
        s.soakaway_feasibility = "test infiltration rate on site"
    else:
        s.notes.append("Soil data unavailable — infiltration/corrosivity not assessed.")

    # Corrosivity + pipe material
    s.soil_corrosivity, s.pipe_material_guidance = _corrosivity(soil)

    # Frost-protected minimum burial depth for pressurised water mains.
    frost = (climate.frost_depth_m if climate else None) or 0.0
    s.min_burial_depth_m = round(max(0.75, frost + 0.3), 2)

    # Trench support / dewatering
    gw = gw_depth_m
    typ_trench = 1.5  # assumed utility trench depth for screening (m)
    if gw is not None and gw <= typ_trench + 0.5:
        s.dewatering = (f"Likely required — measured groundwater at {gw:.1f} m is at/near "
                        "typical trench depth; plan well-point/sump dewatering.")
    elif hydrology and hydrology.nearest_water_m is not None and hydrology.nearest_water_m < 100:
        s.dewatering = "Possible — site is very close to surface water; verify the water table."
    else:
        s.dewatering = "Assess the groundwater table; shallow water would require dewatering."

    if cohesive and (gw is None or gw > typ_trench):
        s.trench_support = ("Stiff cohesive soil may stand briefly in shallow trenches, but "
                            "battering or shoring/trench boxes are still required for worker "
                            "safety and deeper runs.")
    else:
        s.trench_support = ("Granular or wet soils are prone to collapse: provide trench "
                            "boxes/shoring or battered sides, especially below the water table.")

    # Stormwater / drainage
    precip = (climate.annual_precip_mm if climate else None)
    slope = terrain.slope_deg if terrain else None
    if precip is not None:
        wet = climate.wetness_class or ""
        drain_bits = [f"mean annual rainfall ~{precip:.0f} mm ({wet})"]
        if s.infiltration_class in ("Low", "Very low"):
            drain_bits.append("low-permeability soil limits infiltration — size attenuation "
                              "storage and a positive outfall")
        else:
            drain_bits.append("soil permeability supports infiltration SuDS (confirm by test)")
        if slope is not None and slope < 1:
            drain_bits.append("very flat ground — design minimum self-cleansing gradients and "
                              "check for ponding")
        s.stormwater_note = "; ".join(drain_bits) + "."
    else:
        s.notes.append("Climate data unavailable — stormwater design rainfall not derived.")

    # Bedding / backfill
    if cohesive:
        s.bedding_backfill = ("Provide granular bedding/surround (compacted) over soft/clay "
                              "subgrade; consider geotextile separation to prevent fines "
                              "migration and support.")
    elif texture:
        s.bedding_backfill = ("Granular bedding and surround to pipe maker's spec; reuse "
                              "suitable site-won granular material for backfill where compliant.")
    return s
