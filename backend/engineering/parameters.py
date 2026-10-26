"""Assemble preliminary geotechnical design parameters."""
from __future__ import annotations

from typing import Optional

from ..schemas import BearingPoint, Climate, GeotechParameters, SoilProfile, Terrain
from .bearing import (allowable_bearing, elastic_settlement_mm, slope_reduction,
                      settlement_sensitivity)
from .classification import params_for, stiffness_for, seismic_site_class


def _recommend_foundation(q_all: float, settlement_mm: float,
                          slope_deg: Optional[float]) -> str:
    if q_all >= 200 and settlement_mm < 25:
        return "Shallow spread/strip footings (likely feasible)"
    if q_all >= 100 and settlement_mm < 40:
        return "Shallow footings for light loads; raft or wider footings for heavy loads"
    if q_all >= 60:
        return "Raft/mat foundation or ground improvement"
    return "Deep (piled) foundations or significant ground improvement"


def build_parameters(soil: SoilProfile, terrain: Terrain, climate: Climate,
                     width_b_m: float, depth_df_m: float) -> GeotechParameters:
    texture = soil.dominant_usda_texture
    p = params_for(texture)
    es_mpa, vs30 = stiffness_for(texture)

    phi = float(p["phi"])
    c = float(p["cohesion"])
    gamma = float(p["gamma"])

    reduction = slope_reduction(terrain.slope_deg)

    def q_allow(b: float) -> float:
        q_ult, q_all_net = allowable_bearing(c, phi, gamma, b, depth_df_m)
        return q_all_net * reduction

    q_ult, _ = allowable_bearing(c, phi, gamma, width_b_m, depth_df_m)
    q_all_net = q_allow(width_b_m)

    lo, hi = p["bearing"]
    q_all_display = max(min(q_all_net, hi * 1.5), 0.0)

    settlement = elastic_settlement_mm(q_all_display, width_b_m, es_mpa)

    # Bearing-capacity vs footing-width curve for the UI/report.
    curve = [BearingPoint(width_m=round(b, 1),
                          allowable_kpa=round(max(min(q_allow(b), hi * 1.5), 0.0), 0))
             for b in (0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)]

    # Minimum founding depth: deeper of frost line and clay active-zone / input.
    frost = climate.frost_depth_m or 0.0
    active = 0.6 if texture and "clay" in texture.lower() else 0.3
    min_depth = round(max(depth_df_m, frost + 0.1 if frost else 0.0, active), 2)

    desc = p["description"]
    if texture:
        desc = f"{desc} ({texture}; approx. USCS {p['uscs']})"

    return GeotechParameters(
        soil_description=desc,
        friction_angle_deg=phi,
        cohesion_kpa=c,
        unit_weight_kn_m3=gamma,
        elastic_modulus_mpa=es_mpa,
        typical_spt_n=p["spt_n"],
        allowable_bearing_kpa=round(q_all_display, 0),
        ultimate_bearing_kpa=round(q_ult, 0),
        settlement_mm=settlement,
        settlement_sensitivity=settlement_sensitivity(settlement),
        min_founding_depth_m=min_depth,
        seismic_site_class=seismic_site_class(vs30),
        vs30_proxy_mps=vs30,
        recommended_foundation=_recommend_foundation(q_all_display, settlement, terrain.slope_deg),
        bearing_curve=curve,
    )
