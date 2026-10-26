"""Overall site suitability index combining hazards and bearing performance."""
from __future__ import annotations

from ..schemas import GeotechParameters, HazardRating, Suitability, Terrain


def _rating(score: float) -> str:
    if score >= 75:
        return "Favourable"
    if score >= 55:
        return "Marginal"
    if score >= 35:
        return "Challenging"
    return "Severe"


def build_suitability(hazards: list[HazardRating], params: GeotechParameters,
                      terrain: Terrain) -> Suitability | None:
    # Real-only: a suitability score requires a real bearing value; otherwise
    # there is nothing honest to score.
    if params.allowable_bearing_kpa is None:
        return None
    # Only assessed hazards count (ignore "Insufficient data").
    usable = [h for h in hazards if h.level != "Insufficient data"]
    # Hazard component: 1 - weighted mean of hazard scores (seismic weighted up).
    weights = {"Seismicity": 1.4, "Slope instability / landslide": 1.3,
               "Flooding / inundation": 1.2, "Ground motion / subsidence": 1.3}
    wsum = sum(weights.get(h.name, 1.0) for h in usable)
    hazard_mean = (sum(h.score * weights.get(h.name, 1.0) for h in usable) / wsum
                   if wsum else 0)
    hazard_component = (1 - hazard_mean) * 100

    # Bearing component: map net allowable 0..300 kPa onto 0..100.
    bearing = params.allowable_bearing_kpa or 0
    bearing_component = min(bearing / 300.0, 1.0) * 100

    # Settlement penalty.
    settle = params.settlement_mm or 0
    settle_penalty = min(settle / 50.0, 1.0) * 100

    # Slope penalty.
    slope = terrain.slope_deg or 0
    slope_penalty = min(slope / 35.0, 1.0) * 100

    score = (0.5 * hazard_component + 0.3 * bearing_component
             - 0.1 * settle_penalty - 0.1 * slope_penalty)
    score = round(max(min(score, 100), 0), 0)

    drivers: list[str] = []
    for h in sorted(hazards, key=lambda x: -x.score):
        if h.level in ("High", "Very High"):
            drivers.append(f"{h.name}: {h.level}")
    if bearing < 100:
        drivers.append(f"Low bearing capacity (~{bearing:.0f} kPa)")
    if settle >= 25:
        drivers.append(f"High settlement (~{settle:.0f} mm)")
    if slope >= 10:
        drivers.append(f"Steep slope (~{slope:.0f}deg)")
    if not drivers:
        drivers.append("No high-severity constraints identified in screening")

    rating = _rating(score)
    summary = {
        "Favourable": "Conditions appear favourable for conventional development, subject to confirmation.",
        "Marginal": "Workable site with constraints that need engineering attention.",
        "Challenging": "Significant constraints; specialised foundations/mitigation likely required.",
        "Severe": "Severe constraints; detailed investigation and major mitigation essential.",
    }[rating]

    return Suitability(score=score, rating=rating, summary=summary, drivers=drivers[:5])
