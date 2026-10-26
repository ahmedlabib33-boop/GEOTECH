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
