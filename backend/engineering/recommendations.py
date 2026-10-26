"""Generate preliminary recommendations from parameters and hazards."""
from __future__ import annotations

from ..schemas import (GeotechParameters, HazardRating, Recommendation,
                       SeismicContext, SoilProfile, Terrain)


def build_recommendations(terrain: Terrain, soil: SoilProfile,
                          seismic: SeismicContext, params: GeotechParameters,
                          hazards: list[HazardRating]) -> list[Recommendation]:
    recs: list[Recommendation] = []
    hz = {h.name: h for h in hazards}

    # Foundation type
    bearing = params.allowable_bearing_kpa or 0
    if bearing >= 200:
        recs.append(Recommendation(
            category="Foundations",
            text=(f"Preliminary net allowable bearing ~{bearing:.0f} kPa suggests "
                  "conventional shallow spread/strip footings are likely feasible "
                  "for light-to-medium structures, subject to settlement checks.")))
    elif bearing >= 100:
        recs.append(Recommendation(
            category="Foundations",
            text=(f"Preliminary net allowable bearing ~{bearing:.0f} kPa indicates "
                  "shallow footings may suit lighter structures; wider footings, "
                  "a raft, or ground improvement may be needed for heavier loads.")))
    else:
        recs.append(Recommendation(
            category="Foundations",
            text=(f"Low preliminary bearing (~{bearing:.0f} kPa) points to soft/"
                  "compressible ground — consider a raft, ground improvement, or "
                  "deep (piled) foundations pending site investigation.")))

    # Slope
    if hz["Slope instability / landslide"].level in ("High", "Very High"):
        recs.append(Recommendation(
            category="Slope stability",
            text=("Elevated landslide susceptibility: commission a slope-stability "
                  "analysis, control surface/subsurface drainage, and avoid "
                  "undercutting or surcharging the slope.")))
    elif (terrain.slope_deg or 0) >= 5:
        recs.append(Recommendation(
            category="Site grading",
            text=(f"Sloping ground (~{terrain.slope_deg:.0f}deg): plan cut/fill "
                  "balancing, retaining structures, and positive drainage away "
                  "from foundations.")))

    # Seismic
    if hz["Seismicity"].level in ("Moderate", "High", "Very High"):
        pga = f" (indicative PGA ~{seismic.estimated_pga_g}g)" if seismic.estimated_pga_g else ""
        recs.append(Recommendation(
            category="Seismic design",
            text=(f"Region shows {hz['Seismicity'].level.lower()} historical "
                  f"seismicity{pga}. Apply the governing seismic code, obtain a "
                  "site-specific seismic hazard/soil-class study, and detail for "
                  "ductility.")))

    # Liquefaction
    if hz["Liquefaction potential"].level in ("High", "Very High"):
        recs.append(Recommendation(
            category="Liquefaction",
            text=("Liquefaction screening is unfavourable (loose granular soils, "
                  "low-lying, seismic). Investigate groundwater depth and relative "
                  "density (SPT/CPT); consider densification or deep foundations.")))

    # Expansive soil
    if hz["Expansive / shrink-swell soil"].level in ("High", "Very High"):
        recs.append(Recommendation(
            category="Expansive soils",
            text=("Clay-rich near-surface soils may shrink/swell. Run Atterberg "
                  "limits and swell tests; consider moisture control, deepened "
                  "footings below the active zone, or stiffened rafts.")))

    # Drainage / groundwater
    if (terrain.slope_deg or 99) < 3 and (terrain.elevation_m or 999) < 20:
        recs.append(Recommendation(
            category="Drainage / groundwater",
            text=("Flat, low-lying site: investigate groundwater table and flood "
                  "exposure; provide robust site drainage and consider raising "
                  "finished floor levels.")))

    # Always: site investigation
    recs.append(Recommendation(
        category="Mandatory next step",
        text=("Confirm all parameters with an intrusive ground investigation "
              "(boreholes/test pits, SPT/CPT, groundwater monitoring, and "
              "laboratory classification/strength tests) before design.")))
    return recs
