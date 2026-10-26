"""Derive geotechnical parameters from a real borehole log (measured data).

When the user supplies measured ground data it OVERRIDES the satellite soil
estimate. Correlations are standard screening methods:
  - Sand friction angle from SPT: Wolff (1989).
  - Granular allowable bearing: Meyerhof (25 mm settlement).
  - Clay undrained strength from SPT: cu ~ 5*N (kPa); bearing via Nc (phi=0).
These remain preliminary — real lab/CPT values should refine them — but they are
grounded in the site's own measurements rather than a 250 m global model.
"""
from __future__ import annotations

import math
from typing import Optional

from ..schemas import BearingPoint, Borehole, BoreholeLayer, GeotechParameters
from .bearing import elastic_settlement_mm, settlement_sensitivity


def has_usable_data(bh: Optional[Borehole]) -> bool:
    if bh is None:
        return False
    return bool(bh.layers) or bh.groundwater_depth_m is not None


def _is_cohesive(layer: BoreholeLayer) -> bool:
    txt = (layer.description or "").lower()
    us = (layer.uscs or "").upper()
    if us[:1] in ("C",):          # CL, CH
        return True
    if us[:1] in ("S", "G"):      # sands, gravels
        return False
    return any(k in txt for k in ("clay", "silt", "peat", "organic"))


def _founding_layer(bh: Borehole, depth_df_m: float) -> Optional[BoreholeLayer]:
    # Layer that contains the founding depth, else the first below it, else last.
    for lyr in bh.layers:
        if lyr.top_m <= depth_df_m < lyr.bottom_m:
            return lyr
    below = [l for l in bh.layers if l.top_m >= depth_df_m]
    if below:
        return min(below, key=lambda l: l.top_m)
    return bh.layers[-1] if bh.layers else None


def _phi_from_spt(n: float) -> float:
    return round(max(28.0, min(27.1 + 0.3 * n - 0.00054 * n * n, 45.0)), 1)


def _meyerhof_bearing_sand(n: float, b: float, df: float, gw_depth: Optional[float]) -> float:
    """Net allowable bearing (kPa) for 25 mm settlement, Meyerhof."""
    kd = min(1.0 + 0.33 * df / b, 1.33)
    if b <= 1.2:
        q = 12.0 * n * kd
    else:
        q = 8.0 * n * ((b + 0.3) / b) ** 2 * kd
    # Water-table correction: up to 50% reduction when GW at founding level.
    if gw_depth is not None:
        dw = gw_depth - df
        if dw <= 0:
            q *= 0.5
        elif dw < b:
            q *= 0.5 + 0.5 * (dw / b)
    return max(q, 0.0)


def build_parameters_from_borehole(bh: Borehole, width_b_m: float,
                                   depth_df_m: float) -> GeotechParameters:
    layer = _founding_layer(bh, depth_df_m)
    gw = bh.groundwater_depth_m
    n = float(layer.spt_n) if (layer and layer.spt_n is not None) else None
    cohesive = _is_cohesive(layer) if layer else False
    desc = (layer.description or layer.uscs or "founding stratum") if layer else "n/a"

    gamma = 19.0 if cohesive else 18.5

    if cohesive:
        # cu ~ 5*N (kPa); bearing via Nc (phi=0, square-ish shape ~6.2).
        cu = (5.0 * n) if n is not None else 50.0
        phi = 0.0
        q_ult = 6.2 * cu + gamma * depth_df_m
        q_net_all = (6.2 * cu) / 3.0
        es_mpa = max(3.0, 0.3 * cu)       # Eu ~ 300*cu
        spt_txt = f"N={int(n)}" if n is not None else "assumed"
        settle_note_consol = True
    else:
        phi = _phi_from_spt(n) if n is not None else 32.0
        cu = 0.0
        q_net_all = (_meyerhof_bearing_sand(n, width_b_m, depth_df_m, gw)
                     if n is not None else 150.0)
        q_ult = q_net_all * 3.0 + gamma * depth_df_m
        es_mpa = max(5.0, 2.5 * n) if n is not None else 20.0
        spt_txt = f"N={int(n)}" if n is not None else "assumed"
        settle_note_consol = False

    settlement = elastic_settlement_mm(q_net_all, width_b_m, es_mpa)
    sens = settlement_sensitivity(settlement)
    if settle_note_consol:
        sens += " (plus long-term consolidation — assess separately)"

    def q_at(b: float) -> float:
        if cohesive:
            return (6.2 * cu) / 3.0
        return (_meyerhof_bearing_sand(n, b, depth_df_m, gw) if n is not None else 150.0)

    curve = [BearingPoint(width_m=round(b, 1), allowable_kpa=round(q_at(b), 0))
             for b in (0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)]

    min_depth = depth_df_m
    soil_kind = "cohesive (clay/silt)" if cohesive else "granular (sand/gravel)"
    uscs = (layer.uscs if layer and layer.uscs else ("CL" if cohesive else "SP"))

    return GeotechParameters(
        soil_description=f"{desc} — {soil_kind}, measured {spt_txt}"
                         + (f"; USCS {uscs}" if uscs else ""),
        friction_angle_deg=phi,
        cohesion_kpa=round(cu, 0),
        unit_weight_kn_m3=gamma,
        elastic_modulus_mpa=round(es_mpa, 0),
        typical_spt_n=spt_txt,
        allowable_bearing_kpa=round(q_net_all, 0),
        ultimate_bearing_kpa=round(q_ult, 0),
        settlement_mm=settlement,
        settlement_sensitivity=sens,
        min_founding_depth_m=round(min_depth, 2),
        seismic_site_class="(measure Vs for site class)",
        vs30_proxy_mps=None,
        recommended_foundation=_recommend(q_net_all, settlement),
        bearing_curve=curve,
        data_basis="borehole",
    )


def _recommend(q_all: float, settlement_mm: float) -> str:
    if q_all >= 200 and settlement_mm < 25:
        return "Shallow spread/strip footings (from measured data)"
    if q_all >= 100:
        return "Shallow footings for lighter loads; verify settlement"
    if q_all >= 60:
        return "Raft or ground improvement"
    return "Deep (piled) foundations indicated by measured data"
