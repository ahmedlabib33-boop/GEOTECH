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

## Accuracy features

- **Soil uncertainty** — SoilGrids is queried for the **median (Q0.5) and the
  5th/95th percentiles**; the report shows the clay **range** and a **model
  confidence** rating (High/Moderate/Low) from the prediction spread, instead of
  a single point value.
- **Climate normals** — rainfall/temperature are **averaged over the last 5 full
  years** (not a single year) for a more representative normal.

## InSAR ground-motion layer (subsidence / uplift)

Satellite InSAR measures mm/yr ground-surface movement — key for settlement,
sinkholes and slope creep. There is no free, no-login, global live InSAR point
API, so this layer takes the velocity from, in order:

1. a value entered with the request (`insar_velocity_mm_yr`, + uplift / −
   subsidence) — e.g. read off an **EGMS** download or a commercial report;
2. an optional provider set via `INSAR_API_URL` (a URL with `{lat}`/`{lon}`
   placeholders returning JSON with a velocity field).

The velocity becomes a **"Ground motion / subsidence"** hazard (weighted into
the suitability index) with recommendations, a report section, and — for
European sites — a direct **EGMS viewer** link to the measured data.

## Borehole / measured-data override (true accuracy)

Satellite data is a *screen*; measured ground data is the truth. Expand
**"Borehole / measured ground data"** in the UI and enter your real strata
(top/base depth, description, USCS, SPT N) and groundwater depth. When present,
the app computes the foundation parameters from **your data** instead of the
satellite soil model:

- Sand: friction angle from SPT (Wolff 1989); allowable bearing by Meyerhof
  (25 mm settlement) with a water-table correction.
- Clay: undrained strength `cu ≈ 5·N`; bearing via `Nc` (φ=0), with a
  consolidation-settlement note.
- Measured groundwater depth feeds the liquefaction screening.

The report then marks these parameters **"Measured — from borehole"** and shows
the borehole log. API: add a `borehole` object to the `/api/assess` body.

## Optional: Sentinel-2 10 m high-resolution indices (Sentinel Hub)

When credentials are set, the app pulls real **10 m Sentinel-2** indices at the
site via the Sentinel Hub Statistical API (Copernicus Data Space Ecosystem) —
far finer than the 250 m MODIS value, which the 10 m NDVI then replaces:

- **NDVI** — vegetation (also feeds the landslide screening)
- **NDWI** — surface water (>0 suggests open water / inundation)
- **NDMI** — moisture (relevant to expansive clays / drainage)

Get free credentials: register at <https://dataspace.copernicus.eu/>, then
**Sentinel Hub → User settings → OAuth clients → Create**. Set:

```bash
export SENTINELHUB_CLIENT_ID=...
export SENTINELHUB_CLIENT_SECRET=...
# optional overrides: SENTINELHUB_TOKEN_URL, SENTINELHUB_STATS_URL
```

On Vercel, add these under **Project → Settings → Environment Variables** and
redeploy. Without them the app runs normally and omits the high-res panel.

## Optional AI engineering commentary

Tick **"AI engineering commentary"** (or `?ai=true`) to add an LLM-written
*Engineering Commentary* that **interprets the computed data only** — it is
system-prompted to never invent a value and to defer to a ground investigation.
It activates only when an API key is set:

```bash
export ANTHROPIC_API_KEY=sk-ant-...        # required to enable commentary
export GEOTECH_LLM_MODEL=claude-3-5-sonnet-latest   # optional override
```

On Vercel, add `ANTHROPIC_API_KEY` under **Project → Settings → Environment
Variables**. Without a key the app runs normally and simply omits the
commentary. The LLM does **not** make the underlying data more accurate — it
only reads and explains the numbers the pipeline already produced.

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
