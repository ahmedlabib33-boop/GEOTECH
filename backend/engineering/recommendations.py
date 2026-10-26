"""Generate preliminary recommendations from parameters and hazards."""
from __future__ import annotations

from ..schemas import (Climate, GeotechParameters, HazardRating, Hydrology,
                       Recommendation, SeismicContext, SoilProfile, Terrain,
                       Vegetation)


def build_recommendations(terrain: Terrain, soil: SoilProfile,
                          seismic: SeismicContext, params: GeotechParameters,
                          hazards: list[HazardRating],
                          climate: Climate | None = None,
                          vegetation: Vegetation | None = None,
                          hydrology: Hydrology | None = None) -> list[Recommendation]:
    recs: list[Recommendation] = []
    hz = {h.name: h for h in hazards}

    # Real-only: no computed soil parameters → do not fabricate foundation advice.
    if params.data_basis == "unavailable":
        recs.append(Recommendation(
            category="Data availability",
            text=("Core ground data was unavailable for this point, so no bearing or "
                  "settlement estimate could be produced. An intrusive ground "
                  "investigation (boreholes/CPT, laboratory testing) is required to "
                  "establish design parameters.")))
        for h in hazards:
            if h.level in ("High", "Very High"):
                recs.append(Recommendation(category=h.name, text=h.rationale))
        return recs

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

    # Settlement
    if (params.settlement_mm or 0) >= 25:
        recs.append(Recommendation(
            category="Settlement",
            text=(f"Estimated immediate settlement ~{params.settlement_mm:.0f} mm for the "
                  "trial footing may exceed typical 25 mm tolerance — widen the footing, "
                  "reduce bearing pressure, or improve the ground.")))

    # Frost / founding depth
    if climate and (climate.frost_depth_m or 0) >= 0.3:
        recs.append(Recommendation(
            category="Frost protection",
            text=(f"Estimated frost penetration ~{climate.frost_depth_m:.2f} m "
                  f"(freezing index ~{climate.freezing_degree_days:.0f} degC-days). Found "
                  f"footings at least {params.min_founding_depth_m:.2f} m below grade, "
                  "below the frost line.")))

    # Seismic site class amplification
    if params.seismic_site_class and params.seismic_site_class.startswith("E") and \
            hz["Seismicity"].level in ("Moderate", "High", "Very High"):
        recs.append(Recommendation(
            category="Site amplification",
            text=(f"Soft-soil site class ({params.seismic_site_class}, Vs30 proxy "
                  f"~{params.vs30_proxy_mps:.0f} m/s) can amplify ground motion — confirm "
                  "Vs30 by measurement and apply the correct spectral site factors.")))

    # Wet climate drainage
    if climate and climate.wetness_class in ("Wet", "Very wet"):
        recs.append(Recommendation(
            category="Drainage",
            text=(f"{climate.wetness_class} climate (~{climate.annual_precip_mm:.0f} mm/yr): "
                  "design robust surface and subsurface drainage, erosion control, and "
                  "waterproofing; expect a shallow/variable water table.")))

    # Flooding / water proximity
    flood = hz.get("Flooding / inundation")
    if flood and flood.level in ("High", "Very High"):
        extra = ""
        if hydrology and hydrology.nearest_water_m is not None:
            extra = (f" Nearest water ~{hydrology.nearest_water_m:.0f} m "
                     f"({hydrology.nearest_water_type}).")
        recs.append(Recommendation(
            category="Flood risk",
            text=("Elevated flood/inundation exposure: obtain local flood maps and a "
                  "design flood level, raise finished floor levels with freeboard, "
                  "protect foundations against scour and buoyancy, and plan drainage "
                  "and flood defences." + extra)))
    elif flood and flood.level == "Moderate":
        recs.append(Recommendation(
            category="Flood risk",
            text=("Moderate flood exposure: check the site against local flood-zone "
                  "mapping and set finished floor levels with adequate freeboard.")))

    # Ground motion / subsidence (InSAR)
    gm = hz.get("Ground motion / subsidence")
    if gm and gm.level in ("High", "Very High"):
        recs.append(Recommendation(
            category="Ground movement",
            text=("Measured InSAR shows active ground movement: establish a "
                  "deformation-monitoring regime, identify the driver (dewatering, "
                  "consolidation, mining, tectonics), and design foundations and "
                  "services to tolerate the differential movement or mitigate the cause.")))
    elif gm and gm.level == "Moderate":
        recs.append(Recommendation(
            category="Ground movement",
            text=("Mild ground motion detected by InSAR — continue monitoring and "
                  "allow for differential movement in settlement-sensitive structures.")))

    # Vegetation / site clearing (NDVI)
    if vegetation and vegetation.ndvi is not None:
        if vegetation.ndvi >= 0.6:
            recs.append(Recommendation(
                category="Site clearing / topsoil",
                text=(f"Dense vegetation (NDVI {vegetation.ndvi:.2f}): budget for clearing "
                      "and stripping organic topsoil before founding; expect a wetter, "
                      "organic-rich near surface and strong slope root reinforcement.")))
        elif vegetation.ndvi >= 0.3:
            recs.append(Recommendation(
                category="Site clearing / topsoil",
                text=(f"Moderate vegetation (NDVI {vegetation.ndvi:.2f}): strip and stockpile "
                      "organic topsoil; provide erosion/sediment control during works.")))
        elif vegetation.ndvi < 0.1:
            recs.append(Recommendation(
                category="Surface conditions",
                text=(f"Sparse/bare surface (NDVI {vegetation.ndvi:.2f}): verify whether "
                      "shallow rock, duricrust or impervious cover is present, and plan "
                      "wind/water erosion control for exposed ground.")))

    # Always: site investigation
    recs.append(Recommendation(
        category="Mandatory next step",
        text=("Confirm all parameters with an intrusive ground investigation "
              "(boreholes/test pits, SPT/CPT, groundwater monitoring, and "
              "laboratory classification/strength tests) before design.")))
    return recs
