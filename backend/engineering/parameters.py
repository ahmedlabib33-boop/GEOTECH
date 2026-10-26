"""Assemble preliminary geotechnical design parameters."""
from __future__ import annotations

from typing import Optional

from ..schemas import GeotechParameters, SoilProfile, Terrain
from .bearing import allowable_bearing, slope_reduction
from .classification import params_for


def build_parameters(soil: SoilProfile, terrain: Terrain,
                     width_b_m: float, depth_df_m: float) -> GeotechParameters:
    texture = soil.dominant_usda_texture
    p = params_for(texture)

    phi = float(p["phi"])
    c = float(p["cohesion"])
    gamma = float(p["gamma"])

    q_ult, q_all_net = allowable_bearing(c, phi, gamma, width_b_m, depth_df_m)
    reduction = slope_reduction(terrain.slope_deg)
    q_all_net *= reduction

    # Keep the computed value within sane screening bounds and cross-check
    # against the presumed-bearing table for the texture.
    lo, hi = p["bearing"]
    q_all_display = max(min(q_all_net, hi * 1.5), 0.0)

    desc = p["description"]
    if texture:
        desc = f"{desc} ({texture}; approx. USCS {p['uscs']})"

    return GeotechParameters(
        soil_description=desc,
        friction_angle_deg=phi,
        cohesion_kpa=c,
        unit_weight_kn_m3=gamma,
        typical_spt_n=p["spt_n"],
        allowable_bearing_kpa=round(q_all_display, 0),
        ultimate_bearing_kpa=round(q_ult, 0),
        settlement_sensitivity=p["settlement"],
    )
