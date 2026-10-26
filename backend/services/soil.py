"""Soil profile from ISRIC SoilGrids v2.0 (250 m global, no API key).

SoilGrids returns integer "mapped" values that must be divided by a per-property
`d_factor` to reach physical units. We read that factor from the response when
present and apply the documented conversions.
"""
from __future__ import annotations

from typing import Optional

import httpx

from ..schemas import SoilLayer, SoilProfile
from ..engineering.classification import usda_texture, usda_to_uscs

SOILGRIDS = "https://rest.isric.org/soilgrids/v2.0/properties/query"

PROPERTIES = ["clay", "sand", "silt", "bdod", "soc", "phh2o", "cfvo"]
DEPTHS = ["0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm", "100-200cm"]

# Fallback d_factors if the response omits unit_measure.
_FALLBACK_DFACTOR = {
    "clay": 10, "sand": 10, "silt": 10,   # g/kg -> %
    "bdod": 100,                           # cg/cm3 -> kg/dm3
    "soc": 10,                             # dg/kg -> g/kg
    "phh2o": 10,                           # pHx10 -> pH
    "cfvo": 10,                            # per-mille -> vol %
}


def _depth_bounds(label: str) -> tuple[int, int]:
    nums = label.replace("cm", "")
    top, bottom = nums.split("-")
    return int(top), int(bottom)


def _value(layer: dict, depth_label: str, stat: str = "mean") -> Optional[float]:
    for d in layer.get("depths", []):
        if d.get("label") == depth_label:
            vals = d.get("values") or {}
            v = vals.get(stat)
            if v is None and stat != "mean":   # fall back to mean / median
                v = vals.get("mean") or vals.get("Q0.5")
            return None if v is None else float(v)
    return None


def _convert(prop: str, raw_target: Optional[float]) -> Optional[float]:
    """Convert a d_factor-normalised value into the unit we store."""
    if raw_target is None:
        return None
    if prop == "bdod":          # kg/dm3 (== g/cm3) -> kg/m3
        return raw_target * 1000.0
    if prop == "soc":           # g/kg -> percent
        return raw_target / 10.0
    return raw_target           # clay/sand/silt/cfvo already %, phh2o already pH


async def fetch_soil(client: httpx.AsyncClient, lat: float, lon: float) -> SoilProfile:
    # Request the median (Q0.5) and the 5th/95th percentiles so we can report
    # the prediction spread, plus mean for the non-texture properties.
    params = [("lon", lon), ("lat", lat)]
    params += [("value", s) for s in ("mean", "Q0.05", "Q0.5", "Q0.95")]
    params += [("property", p) for p in PROPERTIES]
    params += [("depth", d) for d in DEPTHS]

    r = await client.get(SOILGRIDS, params=params)
    r.raise_for_status()
    layers_meta = (r.json().get("properties") or {}).get("layers", [])

    by_prop: dict[str, dict] = {}
    dfactor: dict[str, float] = {}
    for lm in layers_meta:
        name = lm.get("name")
        if name not in PROPERTIES:
            continue
        by_prop[name] = lm
        um = lm.get("unit_measure") or {}
        dfactor[name] = float(um.get("d_factor") or _FALLBACK_DFACTOR.get(name, 1))

    def prop_value(prop: str, depth: str, stat: str = "mean") -> Optional[float]:
        lm = by_prop.get(prop)
        if lm is None:
            return None
        raw = _value(lm, depth, stat)
        if raw is None:
            return None
        return _convert(prop, raw / (dfactor.get(prop) or 1))

    profile = SoilProfile(source="ISRIC SoilGrids v2.0 (250 m, median + 5th/95th pct)")
    for depth in DEPTHS:
        top, bottom = _depth_bounds(depth)
        # Use the median (Q0.5) for texture; fall back to mean. (Explicit None
        # check — a legitimate 0.0 median must not trigger the fallback.)
        def med(prop: str):
            v = prop_value(prop, depth, "Q0.5")
            return v if v is not None else prop_value(prop, depth)
        clay, sand, silt = med("clay"), med("sand"), med("silt")
        texture = usda_texture(sand, silt, clay)
        layer = SoilLayer(
            depth_label=depth,
            top_cm=top,
            bottom_cm=bottom,
            clay_pct=_round(clay),
            clay_low_pct=_round(prop_value("clay", depth, "Q0.05")),
            clay_high_pct=_round(prop_value("clay", depth, "Q0.95")),
            sand_pct=_round(sand),
            silt_pct=_round(silt),
            coarse_fragments_pct=_round(prop_value("cfvo", depth)),
            bulk_density_kg_m3=_round(prop_value("bdod", depth), 0),
            organic_carbon_pct=_round(prop_value("soc", depth), 2),
            ph=_round(prop_value("phh2o", depth), 1),
            usda_texture=texture,
            uscs_group=usda_to_uscs(texture),
        )
        profile.layers.append(layer)

    _summarise(profile)
    _assign_confidence(profile)
    if not profile.layers:
        profile.note = "No SoilGrids coverage at this location."
    return profile


def _assign_confidence(profile: SoilProfile) -> None:
    """Rate texture confidence from the clay prediction spread (Q0.95-Q0.05)."""
    spreads = [l.clay_high_pct - l.clay_low_pct for l in profile.layers
               if l.clay_high_pct is not None and l.clay_low_pct is not None]
    if not spreads:
        return
    avg = sum(spreads) / len(spreads)
    profile.texture_confidence = (
        "High" if avg < 12 else "Moderate" if avg < 25 else "Low")


def _round(v: Optional[float], ndigits: int = 1) -> Optional[float]:
    return None if v is None else round(v, ndigits)


def _summarise(profile: SoilProfile) -> None:
    """Pick the dominant texture across the foundation-relevant depths (<= 2 m)."""
    counts: dict[str, int] = {}
    for layer in profile.layers:
        if layer.usda_texture:
            counts[layer.usda_texture] = counts.get(layer.usda_texture, 0) + 1
    if counts:
        dominant = max(counts, key=counts.get)
        profile.dominant_usda_texture = dominant
        profile.dominant_uscs_group = usda_to_uscs(dominant)
