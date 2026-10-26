"""Seismic design study: a code-format elastic response spectrum.

Builds a Eurocode 8 (EN 1998-1) horizontal elastic response spectrum Se(T) for
the site from:

 * the **ground type** (A-E) — from the site Vs30 proxy, which sets the soil
   factor S and the corner periods TB, TC, TD;
 * the **spectrum type** (1 for Ms > 5.5, else 2) — chosen from the largest
   magnitude in the real USGS historical catalogue;
 * the **design ground acceleration ag** — a mapped value supplied by the user
   (authoritative, from the national code / hazard map) or, failing that, the
   catalogue-derived screening PGA (clearly flagged as indicative, not a
   probabilistic code value).

Real-only: ag is never invented. With no mapped value and no catalogued
seismicity the spectrum is not plotted — the study says so instead.

This is a screening aid. Final seismic design must use the governing code's
mapped hazard, importance factor and behaviour/response-modification factor.
"""
from __future__ import annotations

from typing import Optional

from ..schemas import SeismicContext, SeismicDesignStudy, SpectrumPoint

# EC8 ground-type parameters (S, TB, TC, TD) at 5% damping (eta = 1).
# Type 1 (higher/far-field, Ms > 5.5) and Type 2 (near-field, Ms <= 5.5).
_GROUND = {
    1: {
        "A": (1.00, 0.15, 0.4, 2.0), "B": (1.20, 0.15, 0.5, 2.0),
        "C": (1.15, 0.20, 0.6, 2.0), "D": (1.35, 0.20, 0.8, 2.0),
        "E": (1.40, 0.15, 0.5, 2.0),
    },
    2: {
        "A": (1.00, 0.05, 0.25, 1.2), "B": (1.35, 0.05, 0.25, 1.2),
        "C": (1.50, 0.10, 0.25, 1.2), "D": (1.80, 0.10, 0.30, 1.2),
        "E": (1.60, 0.05, 0.25, 1.2),
    },
}
_ETA_X_25 = 2.5   # eta * 2.5 at 5% damping


def ec8_ground_type(vs30: Optional[float]) -> Optional[str]:
    """EC8 ground type A-D from Vs30 (m/s). None when Vs30 is unknown."""
    if vs30 is None:
        return None
    if vs30 > 800:
        return "A"
    if vs30 >= 360:
        return "B"
    if vs30 >= 180:
        return "C"
    return "D"


def ec8_spectrum_value(t: float, ag: float, s: float, tb: float, tc: float, td: float) -> float:
    """Horizontal elastic spectral acceleration Se(T) in g (EC8, eta = 1)."""
    if t <= 0:
        return ag * s
    if t <= tb:
        return ag * s * (1.0 + (t / tb) * (_ETA_X_25 - 1.0))
    if t <= tc:
        return ag * s * _ETA_X_25
    if t <= td:
        return ag * s * _ETA_X_25 * (tc / t)
    return ag * s * _ETA_X_25 * (tc * td / (t * t))


def _spectrum_periods(tb: float, tc: float, td: float) -> list[float]:
    pts = set()
    t = 0.0
    while t <= 4.0 + 1e-9:
        pts.add(round(t, 3))
        t += 0.05 if t < 1.0 else 0.1
    pts.update([tb, tc, td, 0.2, 1.0, 4.0])
    return sorted(p for p in pts if 0.0 <= p <= 4.0)


def build_seismic_design(seismic: Optional[SeismicContext],
                         vs30_proxy: Optional[float],
                         user_pga_g: Optional[float] = None) -> Optional[SeismicDesignStudy]:
    unavailable = seismic is None or (seismic.source or "") == "unavailable"
    if unavailable and not user_pga_g:
        return None   # real-only: no seismic context and no mapped value -> no study

    max_mag = None if unavailable else seismic.max_magnitude
    stype = 2 if (max_mag is not None and max_mag <= 5.5) else 1

    gtype = ec8_ground_type(vs30_proxy)
    if gtype is None:
        gtype = "A"
        site_src = ("Vs30 unavailable — reference rock (ground type A); site "
                    "amplification not applied.")
        on_rock = True
    else:
        site_src = f"From Vs30 proxy ~{vs30_proxy:.0f} m/s (EN 1998-1 ground types)."
        on_rock = False
    s, tb, tc, td = _GROUND[stype][gtype]

    study = SeismicDesignStudy(
        ground_type=gtype, site_class_source=site_src, vs30_proxy_mps=vs30_proxy,
        spectrum_type=stype, soil_factor_s=s, t_b_s=tb, t_c_s=tc, t_d_s=td,
    )
    if on_rock:
        study.notes.append(site_src)

    # Design ground acceleration ag (never invented).
    if user_pga_g and user_pga_g > 0:
        ag = float(user_pga_g)
        study.ag_basis = ("User-supplied mapped design ground acceleration "
                          "(national seismic code / hazard map).")
    elif not unavailable and seismic.estimated_pga_g:
        ag = float(seismic.estimated_pga_g)
        study.ag_basis = ("Screening PGA from historical seismicity (USGS catalogue, "
                          "deterministic largest-event proxy) — indicative only, NOT a "
                          "probabilistic code hazard; supply a mapped design PGA for design.")
    else:
        ag = None

    if ag is None:
        study.notes.append(
            "No design ground motion available (no significant catalogued events and no "
            "mapped PGA supplied) — response spectrum not plotted. If the local code "
            "still requires seismic design, enter a mapped design PGA (ag).")
        study.source = "Eurocode 8 (EN 1998-1) format; awaiting an anchor ground motion"
        return study

    study.design_ground_accel_g = round(ag, 3)
    study.spectrum = [
        SpectrumPoint(period_s=t, sa_g=round(ec8_spectrum_value(t, ag, s, tb, tc, td), 4))
        for t in _spectrum_periods(tb, tc, td)
    ]
    study.plateau_sa_g = round(ag * s * _ETA_X_25, 3)
    study.sa_short_g = round(ec8_spectrum_value(0.2, ag, s, tb, tc, td), 3)
    study.sa_1s_g = round(ec8_spectrum_value(1.0, ag, s, tb, tc, td), 3)
    study.importance_note = (
        "Elastic spectrum for importance class II (gamma_I = 1.0). Scale ag by the "
        "importance factor for other classes; divide by the behaviour factor q for a "
        "design (inelastic) spectrum.")
    study.assumptions = [
        f"EC8 Type-{stype} spectrum (chosen from catalogue Mmax "
        f"{'n/a' if max_mag is None else f'{max_mag:.1f}'}; Type 1 if Ms>5.5).",
        f"Ground type {gtype}: S={s}, TB={tb}s, TC={tc}s, TD={td}s; 5% damping.",
        "Horizontal elastic spectrum Se(T); behaviour factor q not applied.",
    ]
    study.source = "Eurocode 8 (EN 1998-1) elastic response spectrum, 5% damping"
    return study
