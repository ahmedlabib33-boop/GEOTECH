"""Pydantic data models shared across the GeoTech Satellite app.

These describe the structured data that flows from the remote-sensing data
sources, through the engineering interpretation layer, and into the report.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Request
# --------------------------------------------------------------------------- #
class BoreholeLayer(BaseModel):
    """One stratum from a real borehole / trial pit / CPT log."""

    top_m: float = Field(ge=0, le=200)
    bottom_m: float = Field(gt=0, le=200)
    description: Optional[str] = Field(None, description="e.g. 'stiff grey CLAY'")
    uscs: Optional[str] = Field(None, description="USCS group, e.g. CL, SP, SM")
    spt_n: Optional[int] = Field(None, ge=0, le=100, description="SPT N (blows/300mm)")


class Borehole(BaseModel):
    """User-supplied measured ground data that overrides the satellite estimate."""

    layers: list[BoreholeLayer] = Field(default_factory=list)
    groundwater_depth_m: Optional[float] = Field(None, ge=0, le=200)
    reference: Optional[str] = Field(None, description="Log ID / investigation ref")


class AssessRequest(BaseModel):
    """Incoming request for a site assessment.

    Either `lat`/`lon` or a `place` name must be supplied. When a place name is
    given it is geocoded to coordinates first.
    """

    lat: Optional[float] = Field(None, ge=-90, le=90)
    lon: Optional[float] = Field(None, ge=-180, le=180)
    place: Optional[str] = Field(None, description="Free-text place name to geocode")
    project_name: Optional[str] = Field(None, description="Label for the report header")
    foundation_width_m: float = Field(
        2.0, gt=0, le=50, description="Assumed footing width B (m) for bearing estimate"
    )
    foundation_depth_m: float = Field(
        1.5, ge=0, le=30, description="Assumed founding depth Df (m) below grade"
    )
    foundation_length_m: Optional[float] = Field(
        None, gt=0, le=100, description="Footing length L (m); defaults to B (square)"
    )
    insar_velocity_mm_yr: Optional[float] = Field(
        None, ge=-500, le=500,
        description="Measured InSAR ground-motion velocity (+uplift/-subsidence)"
    )
    borehole: Optional[Borehole] = Field(
        None, description="Measured ground data; overrides the satellite soil estimate"
    )


# --------------------------------------------------------------------------- #
# Location
# --------------------------------------------------------------------------- #
class Location(BaseModel):
    lat: float
    lon: float
    display_name: Optional[str] = None
    country: Optional[str] = None


# --------------------------------------------------------------------------- #
# Terrain (from Digital Elevation Model)
# --------------------------------------------------------------------------- #
class Terrain(BaseModel):
    elevation_m: Optional[float] = None
    slope_deg: Optional[float] = None
    aspect_deg: Optional[float] = Field(
        None, description="Downslope direction, degrees clockwise from north"
    )
    relief_m: Optional[float] = Field(
        None, description="Max-min elevation across the sampled neighbourhood"
    )
    terrain_class: Optional[str] = None
    source: Optional[str] = None
    note: Optional[str] = None


# --------------------------------------------------------------------------- #
# Soil (from SoilGrids) + engineering interpretation
# --------------------------------------------------------------------------- #
class SoilLayer(BaseModel):
    depth_label: str
    top_cm: int
    bottom_cm: int
    clay_pct: Optional[float] = None
    clay_low_pct: Optional[float] = None   # SoilGrids Q0.05
    clay_high_pct: Optional[float] = None  # SoilGrids Q0.95
    sand_pct: Optional[float] = None
    silt_pct: Optional[float] = None
    coarse_fragments_pct: Optional[float] = None
    bulk_density_kg_m3: Optional[float] = None
    organic_carbon_pct: Optional[float] = None
    ph: Optional[float] = None
    usda_texture: Optional[str] = None
    uscs_group: Optional[str] = None


class SoilProfile(BaseModel):
    layers: list[SoilLayer] = Field(default_factory=list)
    dominant_usda_texture: Optional[str] = None
    dominant_uscs_group: Optional[str] = None
    texture_confidence: Optional[str] = None  # High/Moderate/Low from SoilGrids spread
    source: Optional[str] = None
    note: Optional[str] = None


# --------------------------------------------------------------------------- #
# Seismic (from USGS historical catalogue)
# --------------------------------------------------------------------------- #
class SeismicContext(BaseModel):
    search_radius_km: float
    event_count: int = 0
    max_magnitude: Optional[float] = None
    nearest_significant_km: Optional[float] = None
    largest_event_desc: Optional[str] = None
    hazard_level: Optional[str] = None
    estimated_pga_g: Optional[float] = Field(
        None, description="Order-of-magnitude peak ground acceleration proxy (g)"
    )
    source: Optional[str] = None
    note: Optional[str] = None


# --------------------------------------------------------------------------- #
# Climate (from Open-Meteo reanalysis archive)
# --------------------------------------------------------------------------- #
class Climate(BaseModel):
    year: Optional[int] = None
    years_averaged: Optional[int] = None
    annual_precip_mm: Optional[float] = None
    min_temp_c: Optional[float] = None
    mean_temp_c: Optional[float] = None
    freezing_degree_days: Optional[float] = None
    frost_depth_m: Optional[float] = None
    wetness_class: Optional[str] = None
    source: Optional[str] = None
    note: Optional[str] = None


# --------------------------------------------------------------------------- #
# Ground motion (InSAR line-of-sight / vertical velocity)
# --------------------------------------------------------------------------- #
class GroundMotion(BaseModel):
    velocity_mm_yr: Optional[float] = None   # signed: + uplift, - subsidence
    direction: Optional[str] = None          # "subsidence" / "uplift" / "stable"
    period: Optional[str] = None
    source: Optional[str] = None
    note: Optional[str] = None
    egms_viewer_url: Optional[str] = None


# --------------------------------------------------------------------------- #
# Hydrology (water proximity + riverine flood signal)
# --------------------------------------------------------------------------- #
class Hydrology(BaseModel):
    nearest_water_m: Optional[float] = None
    nearest_water_type: Optional[str] = None
    nearest_water_lat: Optional[float] = None
    nearest_water_lon: Optional[float] = None
    river_discharge_m3s: Optional[float] = None
    height_above_water_m: Optional[float] = None
    source: Optional[str] = None
    note: Optional[str] = None


# --------------------------------------------------------------------------- #
# Sentinel-2 high-resolution indices (Sentinel Hub, 10 m)
# --------------------------------------------------------------------------- #
class SentinelHR(BaseModel):
    ndvi: Optional[float] = None           # vegetation
    ndwi: Optional[float] = None           # surface water (>0 ~ open water)
    ndmi: Optional[float] = None           # moisture
    observation_date: Optional[str] = None
    resolution_m: int = 10
    valid_fraction: Optional[float] = None
    source: Optional[str] = None
    note: Optional[str] = None


# --------------------------------------------------------------------------- #
# Vegetation (Sentinel-2 / MODIS NDVI)
# --------------------------------------------------------------------------- #
class Vegetation(BaseModel):
    ndvi: Optional[float] = None
    observation_date: Optional[str] = None
    cover_class: Optional[str] = None
    ground_description: Optional[str] = None
    source: Optional[str] = None
    note: Optional[str] = None


# --------------------------------------------------------------------------- #
# Engineering-derived parameters & findings
# --------------------------------------------------------------------------- #
class BearingPoint(BaseModel):
    width_m: float
    allowable_kpa: float


class GeotechParameters(BaseModel):
    """Preliminary geotechnical design parameters inferred from surface data."""

    soil_description: Optional[str] = None
    friction_angle_deg: Optional[float] = None
    cohesion_kpa: Optional[float] = None
    unit_weight_kn_m3: Optional[float] = None
    elastic_modulus_mpa: Optional[float] = None
    typical_spt_n: Optional[str] = None
    data_basis: str = "satellite-model"  # or "borehole" (measured)
    allowable_bearing_kpa: Optional[float] = None
    ultimate_bearing_kpa: Optional[float] = None
    settlement_mm: Optional[float] = None
    settlement_sensitivity: Optional[str] = None
    min_founding_depth_m: Optional[float] = Field(
        None, description="Recommended minimum founding depth (frost/active zone)"
    )
    seismic_site_class: Optional[str] = None
    vs30_proxy_mps: Optional[float] = None
    recommended_foundation: Optional[str] = None
    bearing_curve: list[BearingPoint] = Field(default_factory=list)


class Suitability(BaseModel):
    score: float  # 0..100
    rating: str   # Favourable / Marginal / Challenging / Severe
    summary: str
    drivers: list[str] = Field(default_factory=list)


class HazardRating(BaseModel):
    name: str
    level: str  # Low / Moderate / High / Very High
    score: float  # 0..1
    rationale: str


class Recommendation(BaseModel):
    category: str
    text: str


class Assessment(BaseModel):
    """The full assembled assessment that drives the report."""

    project_name: str
    generated_utc: str
    location: Location
    terrain: Terrain
    soil: SoilProfile
    seismic: SeismicContext
    climate: Climate = Field(default_factory=Climate)
    vegetation: Vegetation = Field(default_factory=Vegetation)
    sentinel: Optional[SentinelHR] = None
    hydrology: Hydrology = Field(default_factory=Hydrology)
    ground_motion: Optional[GroundMotion] = None
    borehole: Optional[Borehole] = None
    parameters: GeotechParameters
    suitability: Optional[Suitability] = None
    hazards: list[HazardRating] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    commentary: Optional[str] = None  # optional LLM engineering commentary
    commentary_model: Optional[str] = None
    data_mode: str = "live"  # "live" or "demo"
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = ""
