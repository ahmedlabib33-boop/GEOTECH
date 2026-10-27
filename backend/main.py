"""FastAPI application: serves the map UI and the assessment/report API."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel

from .schemas import AssessRequest, Assessment
from .assess import run_assessment
from .report.pdf import build_pdf, build_compare_pdf
from .services.sitemap import site_image


class CompareRequest(BaseModel):
    sites: list[Assessment]


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(
    title="GeoTech Satellite",
    description="Automated preliminary geotechnical desk study from open "
                "remote-sensing and global geospatial datasets.",
    version="1.0.0",
)


@app.get("/api/health")
async def health():
    from .services.sentinelhub import available as sh_available
    return {"status": "ok",
            "ai_available": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "sentinelhub_available": sh_available()}


@app.post("/api/assess", response_model=Assessment)
async def assess(req: AssessRequest, ai: bool = False):
    try:
        return await run_assessment(req, ai_commentary=ai)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(status_code=502, detail=f"Assessment failed: {e}")


@app.post("/api/report.pdf")
async def report_pdf(req: AssessRequest, ai: bool = False):
    try:
        assessment = await run_assessment(req, ai_commentary=ai)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Fetch a satellite locator image (best-effort).
    img = None
    try:
        img = await site_image(assessment.location.lat, assessment.location.lon)
    except Exception:
        img = None
    pdf = build_pdf(assessment, img)
    safe = "".join(c if c.isalnum() else "_" for c in assessment.project_name)[:40] or "site"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="geotech_{safe}.pdf"'},
    )


@app.post("/api/compare.pdf")
async def compare_pdf(req: CompareRequest):
    if len(req.sites) < 2:
        raise HTTPException(status_code=400, detail="Provide at least two sites to compare.")
    items = [(a.project_name or f"{a.location.lat:.3f},{a.location.lon:.3f}", a)
             for a in req.sites]
    pdf = build_compare_pdf(items)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="geotech_comparison.pdf"'})


@app.get("/api/sitemap.png")
async def sitemap_png(lat: float, lon: float, zoom: int = 17, grid: int = 3):
    """Satellite image of the view: stitched Esri World Imagery (latest
    available mosaic, not a real-time feed) around the point."""
    img = await site_image(lat, lon, zoom=zoom, grid=grid)
    if not img:
        raise HTTPException(status_code=502, detail="Could not build satellite image "
                            "(tile server unreachable or no coverage).")
    return Response(content=img, media_type="image/png",
                    headers={"Content-Disposition":
                             f'attachment; filename="satellite_{lat:.4f}_{lon:.4f}_z{zoom}.png"'})


@app.get("/")
async def index():
    idx = FRONTEND_DIR / "index.html"
    if not idx.exists():
        return JSONResponse({"detail": "frontend not found"}, status_code=404)
    return FileResponse(idx)


# Serve any other static frontend assets (app.js, css) if present.
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
