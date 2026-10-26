"""Screening-level HVAC study from real climate data.

Uses heating/cooling degree-days and design temperatures (from the ERA5
reanalysis) to classify the climate and, when a gross floor area is supplied,
estimate peak heating/cooling loads, equipment sizing and annual energy with a
transparent UA + degree-day method. These are preliminary screening figures for
early planning — a full load calc (e.g. ASHRAE/CIBSE) is required for design.
"""
from __future__ import annotations

from typing import Optional

from ..schemas import Climate, HvacStudy

# Overall screening heat-loss coefficient per m2 of floor (fabric + ventilation
# + infiltration), W/m2.K, by building type. Deliberately typical, not design.
_UA_PER_M2 = {
    "residential": 1.3, "office": 1.6, "retail": 1.8,
    "industrial": 2.0, "warehouse": 1.5,
}
# Internal + solar cooling gain allowance, W/m2 of floor, by type.
_COOL_GAIN_W_M2 = {
    "residential": 25, "office": 45, "retail": 55,
    "industrial": 35, "warehouse": 20,
}
_DEFAULT_TYPE = "office"


def climate_zone(hdd: Optional[float], cdd: Optional[float],
                 wetness: Optional[str]) -> str:
    if hdd is None or cdd is None:
        return "Unknown"
    if cdd >= 1500 and hdd <= 500:
        base = "Very hot"
    elif cdd >= 1000 and hdd <= 1000:
        base = "Hot"
    elif hdd >= 4000:
        base = "Very cold"
    elif hdd >= 3000:
        base = "Cold"
    elif hdd >= 2000:
        base = "Cool temperate"
    elif cdd >= 700:
        base = "Warm"
    else:
        base = "Mixed / temperate"
    humid = ""
    if wetness in ("Wet", "Very wet"):
        humid = " humid"
    elif wetness in ("Arid", "Semi-arid"):
        humid = " dry"
    return base + humid


def _recommend_system(zone: str, cdd: Optional[float], hdd: Optional[float]) -> str:
    z = zone.lower()
    if "very hot" in z or "hot" in z:
        return ("Cooling-led: high-efficiency air-conditioning / VRF or chilled-water "
                "with good solar shading and ventilation; minimal heating.")
    if "very cold" in z or "cold" in z:
        return ("Heating-led: well-insulated envelope with condensing boilers or "
                "air-/ground-source heat pumps and heat recovery ventilation.")
    if "warm" in z:
        return "Cooling-biased heat pumps / split systems; modest heating."
    return ("Balanced: reversible air-source heat pumps suit both seasons; add heat "
            "recovery ventilation.")


def build_hvac(climate: Climate, floor_area_m2: Optional[float] = None,
               building_type: Optional[str] = None) -> Optional[HvacStudy]:
    if climate is None or climate.hdd18 is None or climate.cdd18 is None:
        return None  # real-only: no climate -> no HVAC study

    zone = climate_zone(climate.hdd18, climate.cdd18, climate.wetness_class)
    study = HvacStudy(
        climate_zone=zone, hdd18=climate.hdd18, cdd18=climate.cdd18,
        heating_design_temp_c=climate.heating_design_temp_c,
        cooling_design_temp_c=climate.cooling_design_temp_c,
        recommended_system=_recommend_system(zone, climate.cdd18, climate.hdd18),
        source="Derived from Open-Meteo ERA5 degree-days & design temperatures",
        assumptions=["Indoor set-points 21 degC heating / 24 degC cooling.",
                     "Screening UA + degree-day method; not a design load calc."],
    )

    if floor_area_m2 and floor_area_m2 > 0:
        bt = (building_type or _DEFAULT_TYPE).lower()
        ua = _UA_PER_M2.get(bt, _UA_PER_M2[_DEFAULT_TYPE])          # W/m2.K
        gain = _COOL_GAIN_W_M2.get(bt, _COOL_GAIN_W_M2[_DEFAULT_TYPE])
        study.floor_area_m2 = round(floor_area_m2, 0)
        study.building_type = bt

        hdt = climate.heating_design_temp_c
        cdt = climate.cooling_design_temp_c
        if hdt is not None:
            dT_h = max(study.indoor_heating_setpoint_c - hdt, 0.0)
            study.peak_heating_kw = round(ua * floor_area_m2 * dT_h / 1000.0, 1)
        if cdt is not None:
            dT_c = max(cdt - study.indoor_cooling_setpoint_c, 0.0)
            sensible = ua * floor_area_m2 * dT_c          # envelope gain, W
            internal = gain * floor_area_m2               # internal+solar, W
            study.peak_cooling_kw = round((sensible + internal) / 1000.0, 1)
            study.cooling_tons = round(study.peak_cooling_kw / 3.517, 1)

        # Annual energy via degree-days: E = 24 h * DD * UA * A / 1000 (kWh),
        # heating divided by a seasonal efficiency, cooling by a COP.
        ua_total_kw_per_k = ua * floor_area_m2 / 1000.0
        heat_eff, cop = 0.9, 3.0
        study.annual_heating_kwh = round(24 * climate.hdd18 * ua_total_kw_per_k / heat_eff, 0)
        study.annual_cooling_kwh = round(24 * climate.cdd18 * ua_total_kw_per_k / cop, 0)
        study.assumptions.append(
            f"UA ~{ua} W/m2.K, cooling gains ~{gain} W/m2 ({bt}); heating eff 0.9, cooling COP 3.0.")
    else:
        study.note = "Supply a gross floor area and building type for load/energy sizing."
    return study
