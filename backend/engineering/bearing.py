"""Preliminary bearing capacity (Terzaghi / Vesic general shear).

Shallow strip-footing estimate used only to give an order-of-magnitude
allowable bearing pressure for a desk study. Factor of safety 3.0.
"""
from __future__ import annotations

import math
from typing import Optional

FACTOR_OF_SAFETY = 3.0


def bearing_factors(phi_deg: float) -> tuple[float, float, float]:
    """Return (Nc, Nq, Ngamma). Vesic's Ngamma form."""
    phi = math.radians(phi_deg)
    if phi_deg <= 0:
        return 5.14, 1.0, 0.0
    nq = math.exp(math.pi * math.tan(phi)) * math.tan(math.radians(45 + phi_deg / 2)) ** 2
    nc = (nq - 1.0) / math.tan(phi)
    ngamma = 2.0 * (nq + 1.0) * math.tan(phi)
    return nc, nq, ngamma


def ultimate_bearing(c_kpa: float, phi_deg: float, gamma_kn_m3: float,
                     width_b_m: float, depth_df_m: float) -> float:
    """Gross ultimate bearing capacity q_ult (kPa) for a strip footing."""
    nc, nq, ngamma = bearing_factors(phi_deg)
    q_surcharge = gamma_kn_m3 * depth_df_m
    q_ult = (c_kpa * nc) + (q_surcharge * nq) + (0.5 * gamma_kn_m3 * width_b_m * ngamma)
    return q_ult


def allowable_bearing(c_kpa: float, phi_deg: float, gamma_kn_m3: float,
                      width_b_m: float, depth_df_m: float) -> tuple[float, float]:
    """Return (q_ult, net_allowable) in kPa, FS applied to net capacity."""
    q_ult = ultimate_bearing(c_kpa, phi_deg, gamma_kn_m3, width_b_m, depth_df_m)
    q_surcharge = gamma_kn_m3 * depth_df_m
    q_net_ult = max(q_ult - q_surcharge, 0.0)
    q_all_net = q_net_ult / FACTOR_OF_SAFETY
    return q_ult, q_all_net


def elastic_settlement_mm(q_net_kpa: float, width_b_m: float,
                          es_mpa: float, poisson: float = 0.3,
                          influence: float = 1.0) -> float:
    """Immediate (elastic) settlement of a flexible footing (mm).

    S = q * B * (1 - nu^2) * I / Es.  Indicative screening estimate.
    """
    if es_mpa <= 0:
        return 0.0
    es_kpa = es_mpa * 1000.0
    s_m = q_net_kpa * width_b_m * (1 - poisson ** 2) * influence / es_kpa
    return round(max(s_m, 0.0) * 1000.0, 1)


def settlement_sensitivity(settlement_mm: float) -> str:
    if settlement_mm < 15:
        return "Low (within typical 25 mm tolerance)"
    if settlement_mm < 25:
        return "Moderate (approaching 25 mm limit)"
    if settlement_mm < 50:
        return "High (likely exceeds tolerance — widen footing or improve ground)"
    return "Very high (settlement-governed — deep/raft foundations indicated)"


def shape_factors(phi_deg: float, b: float, l: float, nq: float, nc: float):
    """Vesic shape factors (sc, sq, sgamma) for a B x L footing."""
    bl = min(b / l, 1.0) if l else 1.0
    if phi_deg <= 0:
        return 1 + 0.2 * bl, 1.0, 1.0
    sc = 1 + (nq / nc) * bl
    sq = 1 + bl * math.tan(math.radians(phi_deg))
    sg = max(1 - 0.4 * bl, 0.6)
    return sc, sq, sg


def depth_factors(phi_deg: float, b: float, df: float, nc: float):
    """Vesic depth factors (dc, dq, dgamma)."""
    if b <= 0:
        return 1.0, 1.0, 1.0
    ratio = df / b
    k = ratio if ratio <= 1 else math.atan(ratio)
    if phi_deg <= 0:
        return 1 + 0.4 * k, 1.0, 1.0
    phi = math.radians(phi_deg)
    dq = 1 + 2 * math.tan(phi) * (1 - math.sin(phi)) ** 2 * k
    dc = dq - (1 - dq) / (nc * math.tan(phi))
    return dc, dq, 1.0


def allowable_bearing_full(c_kpa: float, phi_deg: float, gamma_kn_m3: float,
                           b: float, l: float, df: float,
                           gw_depth_m: Optional[float] = None,
                           fs: float = FACTOR_OF_SAFETY):
    """Vesic general bearing capacity with shape, depth and groundwater effects.

    Returns (q_ult_gross, q_net_allowable) in kPa.
    """
    nc, nq, ng = bearing_factors(phi_deg)
    sc, sq, sg = shape_factors(phi_deg, b, l, nq, nc)
    dc, dq, dg = depth_factors(phi_deg, b, df, nc)

    gw = 9.81  # unit weight of water
    gamma_eff_surcharge = gamma_kn_m3
    gamma_eff_base = gamma_kn_m3
    if gw_depth_m is not None:
        if gw_depth_m <= df:                      # water at/above founding level
            gamma_eff_surcharge = max(gamma_kn_m3 - gw, 1.0)
            gamma_eff_base = max(gamma_kn_m3 - gw, 1.0)
        elif gw_depth_m < df + b:                 # within the failure wedge
            frac = (gw_depth_m - df) / b
            gamma_eff_base = max(gamma_kn_m3 - gw * (1 - frac), 1.0)

    q_sur = gamma_eff_surcharge * df              # effective overburden at base
    q_ult = (c_kpa * nc * sc * dc
             + q_sur * nq * sq * dq
             + 0.5 * gamma_eff_base * b * ng * sg * dg)
    q_net_ult = max(q_ult - q_sur, 0.0)
    return q_ult, q_net_ult / fs


def slope_reduction(slope_deg: Optional[float]) -> float:
    """Reduction factor applied to allowable bearing on sloping ground."""
    if slope_deg is None or slope_deg < 5:
        return 1.0
    if slope_deg < 10:
        return 0.85
    if slope_deg < 20:
        return 0.65
    if slope_deg < 30:
        return 0.45
    return 0.30
