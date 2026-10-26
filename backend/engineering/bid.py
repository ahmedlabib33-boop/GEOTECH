"""Bid risk register — a synthesis layer for the tender/bidding phase.

Rolls the site's real findings (geohazards, foundation parameters, logistics,
construction workability, regulatory context) into a weighted risk register
with a contingency driver per line and an overall bid-risk index. It invents no
new data: every line is traceable to an upstream real result, and a line whose
inputs were unavailable is marked 'Insufficient data' and left out of the index.
"""
from __future__ import annotations

from typing import Optional

from ..schemas import (BidRiskItem, BidRiskRegister, ConstructionClimate,
                       CountryContext, GeotechParameters, HazardRating, SiteLogistics)

_WEIGHTS = {
    "Ground & foundations": 1.3, "Seismic": 1.2, "Flooding": 1.0,
    "Slope stability": 0.9, "Problem soils": 0.8, "Logistics & mobilization": 1.1,
    "Construction climate": 0.9, "Regulatory / standards": 0.7,
}
_LOGI = {"Easy": 0.15, "Moderate": 0.4, "Difficult": 0.7, "Remote": 0.9}
_WORK = {"Excellent": 0.1, "Good": 0.25, "Moderate": 0.45,
         "Constrained": 0.7, "Severely constrained": 0.9}


def _level(score: float) -> str:
    if score < 0.25:
        return "Low"
    if score < 0.5:
        return "Moderate"
    if score < 0.75:
        return "High"
    return "Very High"


def _hazard(hazards: list[HazardRating], name: str):
    for h in hazards:
        if h.name == name:
            return h
    return None


def _foundation_item(params: GeotechParameters) -> BidRiskItem:
    if params is None or params.data_basis == "unavailable":
        return BidRiskItem(
            category="Ground & foundations", level="Insufficient data", score=0.0,
            rationale="No usable soil data at this point — foundations cannot be priced "
                      "from the desk study.",
            contingency_driver="Intrusive ground investigation (boreholes/CPT) before tender.")
    rec = (params.recommended_foundation or "").lower()
    if "deep" in rec or "significant ground improvement" in rec:
        score, driver = 0.8, "Piled foundations / ground improvement — major cost item."
    elif "raft" in rec or "ground improvement" in rec:
        score, driver = 0.55, "Raft/mat or ground improvement; price accordingly."
    elif "light loads" in rec:
        score, driver = 0.4, "Shallow footings for light loads; heavier loads need rafts."
    else:
        score, driver = 0.2, "Shallow spread/strip footings likely feasible."
    if (params.settlement_mm or 0) > 50:
        score = min(1.0, score + 0.1)
    if params.allowable_bearing_kpa is not None and params.allowable_bearing_kpa < 75:
        score = min(1.0, score + 0.1)
    rationale = (f"{params.recommended_foundation or 'Foundation type indicative'}; "
                 f"allowable bearing ~{params.allowable_bearing_kpa or 'n/a'} kPa, "
                 f"settlement ~{params.settlement_mm or 'n/a'} mm "
                 f"({params.data_basis}).")
    return BidRiskItem(category="Ground & foundations", level=_level(score), score=round(score, 2),
                       rationale=rationale, contingency_driver=driver)


def _from_hazard(hazards, name, category, driver) -> Optional[BidRiskItem]:
    h = _hazard(hazards, name)
    if h is None:
        return None
    if h.level == "Insufficient data":
        return BidRiskItem(category=category, level="Insufficient data", score=0.0,
                           rationale=h.rationale)
    return BidRiskItem(category=category, level=_level(h.score), score=round(h.score, 2),
                       rationale=h.rationale,
                       contingency_driver=driver if h.score >= 0.5 else None)


def build_bid_risk(hazards: list[HazardRating], params: GeotechParameters,
                   logistics: Optional[SiteLogistics],
                   construction_climate: Optional[ConstructionClimate],
                   country: Optional[CountryContext]) -> BidRiskRegister:
    items: list[BidRiskItem] = [_foundation_item(params)]

    seis = _from_hazard(hazards, "Seismicity", "Seismic",
                        "Seismic detailing, heavier frames/foundations.")
    if seis:
        items.append(seis)
    flood = _from_hazard(hazards, "Flooding / inundation", "Flooding",
                         "Platform raising, drainage, flood-proofing.")
    if flood:
        items.append(flood)
    slope = _from_hazard(hazards, "Slope instability / landslide", "Slope stability",
                         "Slope stabilisation, retaining works, temporary works.")
    if slope:
        items.append(slope)

    # Problem soils: worst of expansive / liquefaction.
    probs = [h for h in (_hazard(hazards, "Expansive / shrink-swell soil"),
                         _hazard(hazards, "Liquefaction potential")) if h]
    real = [h for h in probs if h.level != "Insufficient data"]
    if real:
        worst = max(real, key=lambda h: h.score)
        items.append(BidRiskItem(
            category="Problem soils", level=_level(worst.score), score=round(worst.score, 2),
            rationale=f"{worst.name}: {worst.rationale}",
            contingency_driver=("Ground improvement / soil replacement / specialised foundations."
                                if worst.score >= 0.5 else None)))
    elif probs:
        items.append(BidRiskItem(category="Problem soils", level="Insufficient data", score=0.0,
                                 rationale="Expansive/liquefaction not assessed (no soil data)."))

    if logistics and logistics.mobilization_rating:
        sc = _LOGI.get(logistics.mobilization_rating, 0.5)
        items.append(BidRiskItem(
            category="Logistics & mobilization", level=_level(sc), score=round(sc, 2),
            rationale=f"Mobilization {logistics.mobilization_rating.lower()} — {logistics.access_note}.",
            contingency_driver=("Import of plant/materials, haul roads, camp, long supply lines."
                                if sc >= 0.5 else None)))

    if construction_climate and construction_climate.workability_rating:
        sc = _WORK.get(construction_climate.workability_rating, 0.4)
        items.append(BidRiskItem(
            category="Construction climate", level=_level(sc), score=round(sc, 2),
            rationale=(f"~{construction_climate.workable_days_per_year} workable days/yr "
                       f"({construction_climate.workability_rating.lower()})."),
            contingency_driver=("Weather downtime, seasonal working, programme float."
                                if sc >= 0.5 else None)))

    if country:
        known = bool(country.structural_code)
        sc = 0.3 if known else 0.55
        items.append(BidRiskItem(
            category="Regulatory / standards", level=_level(sc), score=round(sc, 2),
            rationale=("Likely code: " + country.structural_code if known
                       else "Governing design code not identified from the reference table."),
            contingency_driver=("Local code gap analysis, local design-check/PE sign-off, "
                                "permitting.") if not known else "Local design-check / permitting."))

    scored = [(it, _WEIGHTS.get(it.category, 1.0)) for it in items if it.level != "Insufficient data"]
    reg = BidRiskRegister(items=items, source="Synthesis of the desk-study findings (real-only)")
    if scored:
        wsum = sum(w for _, w in scored)
        idx = 100.0 * sum(it.score * w for it, w in scored) / wsum
        reg.index = round(idx, 0)
        reg.overall_rating = _level(idx / 100.0)
        top = sorted(scored, key=lambda x: x[0].score * x[1], reverse=True)[:3]
        drivers = [it.category for it, _ in top if it.score >= 0.5]
        gaps = [it.category for it in items if it.level == "Insufficient data"]
        parts = [f"Overall bid-risk {reg.overall_rating.lower()} ({reg.index:.0f}/100)."]
        if drivers:
            parts.append("Main drivers: " + ", ".join(drivers) + ".")
        if gaps:
            parts.append("Data gaps to close before tender: " + ", ".join(gaps) + ".")
        reg.summary = " ".join(parts)
    else:
        reg.summary = "Insufficient real data to compute a bid-risk index."
    return reg
