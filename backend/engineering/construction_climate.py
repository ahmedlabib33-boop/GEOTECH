"""Construction workability from the real ERA5 daily climate record.

Turns the mean-days-per-year counts computed in services.climate (heavy rain,
extreme heat, frost) into an estimated number of workable days per year, a
workability rating and a short programme note (wettest/driest months). These
are screening indicators for a bid programme / preliminaries, not a substitute
for a site-specific construction schedule.
"""
from __future__ import annotations

from typing import Optional

from ..schemas import Climate, ConstructionClimate


def _rating(workable: int) -> str:
    if workable >= 320:
        return "Excellent"
    if workable >= 280:
        return "Good"
    if workable >= 230:
        return "Moderate"
    if workable >= 180:
        return "Constrained"
    return "Severely constrained"


def build_construction_climate(climate: Climate) -> Optional[ConstructionClimate]:
    if climate is None or climate.annual_precip_mm is None:
        return None   # real-only: no climate record -> no workability study

    rain = int(climate.heavy_rain_days or 0)
    heat = int(climate.extreme_heat_days or 0)
    frost = int(climate.frost_days or 0)

    # Non-working-day estimate: heavy-rain days plus the part of heat/frost days
    # that would halt most trades (de-rated so overlapping effects aren't double
    # counted). Bounded to a sensible range.
    lost = rain + 0.5 * heat + 0.7 * frost
    workable = int(max(120, min(365, round(365 - lost))))

    study = ConstructionClimate(
        workable_days_per_year=workable, workability_rating=_rating(workable),
        heavy_rain_days=rain, extreme_heat_days=heat, frost_days=frost,
        wettest_month=climate.wettest_month, driest_month=climate.driest_month,
        source="Derived from Open-Meteo ERA5 daily record (mean days/yr)",
    )
    if climate.wettest_month:
        study.notes.append(
            f"Wettest month ~{climate.wettest_month}; driest ~{climate.driest_month}. "
            "Plan earthworks and the critical path around the dry window.")
    if heat >= 30:
        study.notes.append(f"~{heat} days/yr over 35 C — allow for heat-stress rules, "
                           "night working and hot-weather concreting.")
    if frost >= 30:
        study.notes.append(f"~{frost} days/yr below 0 C — allow for winter shutdowns, "
                           "frost protection and cold-weather concreting.")
    if rain >= 60:
        study.notes.append(f"~{rain} heavy-rain days/yr — dewatering, haul-road and "
                           "earthworks downtime likely; build float into the programme.")
    return study
