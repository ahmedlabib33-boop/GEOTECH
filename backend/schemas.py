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
    building_floor_area_m2: Optional[float] = Field(
        None, gt=0, le=1_000_000, description="Gross floor area for HVAC load screening"
    )
    building_type: Optional[str] = Field(
        None, description="residential | office | retail | industrial | warehouse"
    )
    design_pga_g: Optional[float] = Field(
        None, ge=0, le=3,
        description="Mapped design peak ground acceleration ag (g) from the national "
                    "seismic code / hazard map; anchors the design response spectrum"
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
    max_temp_c: Optional[float] = None
    freezing_degree_days: Optional[float] = None
    frost_depth_m: Optional[float] = None
    wetness_class: Optional[str] = None
    # Degree-days and design conditions (for HVAC)
    hdd18: Optional[float] = Field(None, description="Heating degree-days, base 18C (annual)")
    cdd18: Optional[float] = Field(None, description="Cooling degree-days, base 18C (annual)")
    heating_design_temp_c: Optional[float] = Field(None, description="~99% winter design temp")
    cooling_design_temp_c: Optional[float] = Field(None, description="~1% summer design temp")
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


# --------------------------------------------------------------------------- #
# HVAC study (from real climate, screening level)
# --------------------------------------------------------------------------- #
class HvacStudy(BaseModel):
    climate_zone: Optional[str] = None
    hdd18: Optional[float] = None
    cdd18: Optional[float] = None
    heating_design_temp_c: Optional[float] = None
    cooling_design_temp_c: Optional[float] = None
    indoor_heating_setpoint_c: float = 21.0
    indoor_cooling_setpoint_c: float = 24.0
    # Load screening (only when a floor area is supplied)
    floor_area_m2: Optional[float] = None
    building_type: Optional[str] = None
    peak_heating_kw: Optional[float] = None
    peak_cooling_kw: Optional[float] = None
    cooling_tons: Optional[float] = None
    annual_heating_kwh: Optional[float] = None
    annual_cooling_kwh: Optional[float] = None
    recommended_system: Optional[str] = None
    assumptions: list[str] = Field(default_factory=list)
    source: Optional[str] = None
    note: Optional[str] = None


# --------------------------------------------------------------------------- #
# Underground networks / excavation study
# --------------------------------------------------------------------------- #
class UndergroundStudy(BaseModel):
    infiltration_class: Optional[str] = None       # permeability of near-surface soil
    soakaway_feasibility: Optional[str] = None
    soil_corrosivity: Optional[str] = None
    pipe_material_guidance: Optional[str] = None
    min_burial_depth_m: Optional[float] = None       # frost-protected cover
    trench_support: Optional[str] = None
    dewatering: Optional[str] = None
    stormwater_note: Optional[str] = None
    bedding_backfill: Optional[str] = None
    notes: list[str] = Field(default_factory=list)
    source: Optional[str] = None


# --------------------------------------------------------------------------- #
# Wind & snow load study (from real ERA5 extremes, screening level)
# --------------------------------------------------------------------------- #
class WindSnowStudy(BaseModel):
    years_analyzed: Optional[int] = None
    return_period_years: int = 50
    # Wind
    mean_annual_max_gust_ms: Optional[float] = None
    design_gust_ms: Optional[float] = None           # T-year Gumbel 10 m gust
    design_gust_kmh: Optional[float] = None
    basic_velocity_pressure_kpa: Optional[float] = None  # q = 0.5*rho*V^2
    indicative_wall_pressure_kpa: Optional[float] = None  # q * combined Cp
    dominant_wind_dir: Optional[str] = None
    wind_class: Optional[str] = None
    # Snow
    max_observed_snow_depth_m: Optional[float] = None
    design_snow_depth_m: Optional[float] = None       # T-year Gumbel depth
    ground_snow_load_kpa: Optional[float] = None
    roof_snow_load_kpa: Optional[float] = None
    snow_zone: Optional[str] = None                   # Negligible..Very heavy
    assumptions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    source: Optional[str] = None


# --------------------------------------------------------------------------- #
# Seismic design study (code-format elastic response spectrum)
# --------------------------------------------------------------------------- #
class SpectrumPoint(BaseModel):
    period_s: float
    sa_g: float


class SeismicDesignStudy(BaseModel):
    code_basis: str = "Eurocode 8 (EN 1998-1) elastic response spectrum, 5% damping"
    ground_type: Optional[str] = None          # EC8 ground type A..E
    site_class_source: Optional[str] = None     # how the ground type was derived
    vs30_proxy_mps: Optional[float] = None
    spectrum_type: Optional[int] = None         # EC8 Type 1 (Ms>5.5) or Type 2
    design_ground_accel_g: Optional[float] = None   # ag on type-A ground (g)
    ag_basis: Optional[str] = None              # mapped value vs catalogue screening
    soil_factor_s: Optional[float] = None
    t_b_s: Optional[float] = None
    t_c_s: Optional[float] = None
    t_d_s: Optional[float] = None
    plateau_sa_g: Optional[float] = None        # constant-acceleration plateau ag*S*2.5
    sa_short_g: Optional[float] = None           # Se(0.2 s)
    sa_1s_g: Optional[float] = None              # Se(1.0 s)
    importance_note: Optional[str] = None
    spectrum: list[SpectrumPoint] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    source: Optional[str] = None


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
    hvac: Optional[HvacStudy] = None
    underground: Optional[UndergroundStudy] = None
    wind_snow: Optional[WindSnowStudy] = None
    seismic_design: Optional[SeismicDesignStudy] = None
    hazards: list[HazardRating] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    commentary: Optional[str] = None  # optional LLM engineering commentary
    commentary_model: Optional[str] = None
    data_mode: str = "live"  # always "live" (real-only); field kept for compatibility
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = ""
