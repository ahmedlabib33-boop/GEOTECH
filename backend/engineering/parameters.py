"""Assemble preliminary geotechnical design parameters (satellite path)."""
from __future__ import annotations

from typing import Optional

from ..schemas import BearingPoint, Climate, GeotechParameters, SoilProfile, Terrain
from .bearing import (allowable_bearing_full, elastic_settlement_mm, slope_reduction,
                      settlement_sensitivity)
from .classification import params_for, stiffness_for, seismic_site_class, usda_to_uscs


def _influence_weighted(soil: SoilProfile, df_m: float, b_m: float) -> tuple[dict, str]:
    """Thickness-weighted soil parameters over the stress-influence zone
    (Df to Df+1.5B, clipped to available data). Returns (params_dict, texture)."""
    z_top = df_m * 100.0                     # cm
    z_bot = (df_m + 1.5 * b_m) * 100.0
    acc = {"phi": 0.0, "cohesion": 0.0, "gamma": 0.0, "es": 0.0, "vs30": 0.0}
    total = 0.0
    tex_weight: dict[str, float] = {}
    for layer in soil.layers:
        overlap = max(0.0, min(z_bot, layer.bottom_cm) - max(z_top, layer.top_cm))
        if overlap <= 0 or not layer.usda_texture:
            continue
        p = params_for(layer.usda_texture)
        es, vs = stiffness_for(layer.usda_texture)
        acc["phi"] += p["phi"] * overlap
        acc["cohesion"] += p["cohesion"] * overlap
        acc["gamma"] += p["gamma"] * overlap
        acc["es"] += es * overlap
        acc["vs30"] += vs * overlap
        tex_weight[layer.usda_texture] = tex_weight.get(layer.usda_texture, 0) + overlap
        total += overlap

    if total <= 0:                           # zone below data (Df > 2 m): use deepest
        for layer in reversed(soil.layers):
            if layer.usda_texture:
                p = params_for(layer.usda_texture)
                es, vs = stiffness_for(layer.usda_texture)
                return ({"phi": p["phi"], "cohesion": p["cohesion"], "gamma": p["gamma"],
                         "es": es, "vs30": vs, "bearing": p["bearing"],
                         "spt_n": p["spt_n"], "description": p["description"],
                         "uscs": p["uscs"]}, layer.usda_texture)
        p = params_for(None)
        es, vs = stiffness_for(None)
        return ({**p, "es": es, "vs30": vs}, soil.dominant_usda_texture)

    dominant = max(tex_weight, key=tex_weight.get)
    base = params_for(dominant)
    return ({"phi": acc["phi"] / total, "cohesion": acc["cohesion"] / total,
             "gamma": acc["gamma"] / total, "es": acc["es"] / total,
             "vs30": acc["vs30"] / total, "bearing": base["bearing"],
             "spt_n": base["spt_n"], "description": base["description"],
             "uscs": base["uscs"]}, dominant)


def build_parameters(soil: SoilProfile, terrain: Terrain, climate: Climate,
                     width_b_m: float, depth_df_m: float,
                     length_l_m: Optional[float] = None) -> GeotechParameters:
    length_l_m = length_l_m or width_b_m     # square by default
    p, texture = _influence_weighted(soil, depth_df_m, width_b_m)

    phi = round(float(p["phi"]), 1)
    c = round(float(p["cohesion"]), 1)
    gamma = round(float(p["gamma"]), 1)
    es_mpa = round(float(p["es"]), 0)
    vs30 = round(float(p["vs30"]), 0)

    reduction = slope_reduction(terrain.slope_deg)

    def q_allow(b: float) -> float:
        _, q_net = allowable_bearing_full(c, phi, gamma, b, length_l_m, depth_df_m)
        return q_net * reduction

    q_ult, q_all_net = allowable_bearing_full(c, phi, gamma, width_b_m, length_l_m, depth_df_m)
    q_all_net *= reduction

    hi = p["bearing"][1]
    q_all_display = max(min(q_all_net, hi * 2.0), 0.0)

    settlement = elastic_settlement_mm(q_all_display, width_b_m, es_mpa)

    curve = [BearingPoint(width_m=round(b, 1),
                          allowable_kpa=round(max(min(q_allow(b), hi * 2.0), 0.0), 0))
             for b in (0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)]

    frost = climate.frost_depth_m or 0.0
    active = 0.6 if texture and "clay" in texture.lower() else 0.3
    min_depth = round(max(depth_df_m, frost + 0.1 if frost else 0.0, active), 2)

    desc = p["description"]
    if texture:
        desc = (f"{desc} (influence-zone weighted; dominant {texture}, "
                f"approx. USCS {usda_to_uscs(texture)})")

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
        recommended_foundation=_recommend(q_all_display, settlement, terrain.slope_deg),
        bearing_curve=curve,
        data_basis="satellite-model",
    )


def _recommend(q_all: float, settlement_mm: float, slope_deg: Optional[float]) -> str:
    if q_all >= 200 and settlement_mm < 25:
        return "Shallow spread/strip footings (likely feasible)"
    if q_all >= 100 and settlement_mm < 40:
        return "Shallow footings for light loads; raft/wider footings for heavy loads"
    if q_all >= 60:
        return "Raft/mat foundation or ground improvement"
    return "Deep (piled) foundations or significant ground improvement"
