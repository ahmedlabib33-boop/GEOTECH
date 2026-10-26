# 🛰️ GeoTech Satellite

**Automated preliminary geotechnical desk study for any point on Earth**, built
from open remote-sensing and global geospatial datasets — no API keys required.

Pick a location on a live satellite map (or search a place name) and the app
pulls terrain, soil and seismic data, runs standard geotechnical
interpretation, and produces an on-screen report plus a downloadable PDF.

---

## ⚠️ What this is — and is not

A full geotechnical report requires **subsurface investigation** (boreholes,
SPT/CPT, groundwater monitoring, laboratory soil tests). Satellites cannot drill
holes. This tool produces a **Phase-1 / desk-study screening** from surface and
modelled data — exactly the kind of preliminary assessment engineers do *before*
mobilising a drilling rig. Soil strength parameters and bearing capacities are
**indicative screening estimates, not design values**, and must be confirmed by
a site-specific investigation by a qualified geotechnical engineer.

## Real data sources (live mode, the default)

| Domain | Source | Notes |
|--------|--------|-------|
| Terrain (elevation, slope, aspect) | [OpenTopoData](https://www.opentopodata.org/) — SRTM 30 m | Horn's method on a 3×3 DEM window |
| Soil (clay/sand/silt, density, pH, SOC) | [ISRIC SoilGrids v2.0](https://soilgrids.org/) — 250 m global | USDA texture → approx. USCS group |
| Seismicity | [USGS Earthquake Catalog](https://earthquake.usgs.gov/) | M≥4 events within 300 km |
| Climate (rainfall, temperature, frost) | [Open-Meteo ERA5](https://open-meteo.com/) reanalysis | annual precip + freezing-degree-days |
| Vegetation / NDVI | [NASA ORNL MODIS](https://modis.ornl.gov/) MOD13Q1 (250 m) | topsoil/clearing, erosion, root reinforcement |
| Sentinel-2 imagery | [EOX Sentinel-2 cloudless](https://s2maps.eu/) basemap | selectable map layer (modified Copernicus data) |
| Water proximity | [OpenStreetMap Overpass](https://overpass-api.de/) | nearest river/lake/coastline + distance |
| River discharge / flood | [Open-Meteo Flood API](https://open-meteo.com/en/docs/flood-api) (GloFAS) | riverine flood magnitude signal |
| Geocoding | [OSM Nominatim](https://nominatim.org/) | place name ⇄ coordinates |
| Satellite basemap | Esri World Imagery tiles | with street / topographic layers |

All are free and keyless. Live mode is the default; **demo mode** (a checkbox,
or `GEOTECH_DEMO=1`) substitutes clearly-labelled sample data so the app runs
with no internet.

## Engineering performed

- **Soil classification** — USDA textural-triangle algorithm → approximate USCS
  group, per depth layer (0–200 cm).
- **Design parameters** — friction angle φ′, cohesion c, unit weight γ, typical
  SPT N, from standard reference ranges.
- **Bearing capacity** — Terzaghi/Vesic general-shear, strip footing, FS = 3.0,
  with a slope-angle reduction factor.
- **Geohazard screening** — flooding/inundation, slope instability/landslide,
  seismicity, expansive/shrink-swell soil, and liquefaction potential, each
  rated Low → Very High with its rationale.
- **Flood & water proximity** — nearest surface water (with a map marker/line),
  GloFAS river discharge, and a flood rating from low/flat terrain + water
  proximity + discharge + rainfall.
- **Settlement** — immediate elastic settlement for the trial footing (mm).
- **Frost penetration** — modified-Berggren depth from freezing-degree-days →
  minimum founding depth.
- **Seismic site class** — NEHRP/EC8-style class from a Vs30 proxy.
- **Bearing vs footing-width curve** — allowable pressure across footing sizes.
- **Site Suitability Index (0–100)** — overall score + rating (Favourable →
  Severe) combining hazards, bearing, settlement and slope.
- **Recommendations** — foundation type, settlement, frost, drainage, slope,
  seismic design, and the mandatory ground-investigation next step.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

uvicorn backend.main:app --reload   # or: ./run.sh
# open http://127.0.0.1:8000
```

Click the map (or search a place), set the project name and trial footing size,
then **Generate assessment** and **Download PDF report**.

To try it with no internet: tick **Demo mode**, or
`GEOTECH_DEMO=1 uvicorn backend.main:app`.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/assess?demo=false` | JSON assessment for a location |
| `POST` | `/api/report.pdf?demo=false` | PDF report download |
| `GET`  | `/api/health` | liveness probe |

Request body:

```json
{ "lat": 30.0444, "lon": 31.2357, "project_name": "Site A",
  "foundation_width_m": 2.0, "foundation_depth_m": 1.5 }
```
(or `{"place": "Cairo", ...}` instead of lat/lon).

## Project layout

```
backend/
  schemas.py            Pydantic models
  assess.py             orchestrator (concurrent fetch + graceful fallback)
  services/             data sources: terrain, soil, seismic, geocoding, demo
  engineering/          classification, bearing, hazards, recommendations
  report/pdf.py         ReportLab PDF generator
  main.py               FastAPI app
frontend/               Leaflet satellite map UI (index.html, app.js, style.css)
tests/                  pytest suite (offline)
```

## Tests

```bash
pytest -q
```

## Running inside a restricted-network environment

If the data-source hosts are blocked (e.g. a locked-down cloud container), live
calls degrade to sample data with a visible warning. Allow these domains to get
real data: `api.opentopodata.org`, `rest.isric.org`, `earthquake.usgs.gov`,
`nominatim.openstreetmap.org`.

## Roadmap ideas

- Google Earth Engine / Sentinel-2 imagery, NDVI, InSAR subsidence
- Global flood-hazard and groundwater layers
- Seismic hazard from a code map (e.g. GSHAP/national codes) rather than catalogue only
- Multi-point / polygon site assessment and comparison
