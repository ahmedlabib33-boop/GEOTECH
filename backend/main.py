"""FastAPI application: serves the map UI and the assessment/report API."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .schemas import AssessRequest, Assessment
from .assess import run_assessment
from .report.pdf import build_pdf
from .services.sitemap import site_image

# Global offline switch: set GEOTECH_DEMO=1 to force sample data everywhere.
FORCE_DEMO = os.environ.get("GEOTECH_DEMO", "").lower() in ("1", "true", "yes")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(
    title="GeoTech Satellite",
    description="Automated preliminary geotechnical desk study from open "
                "remote-sensing and global geospatial datasets.",
    version="1.0.0",
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "force_demo": FORCE_DEMO,
            "ai_available": bool(os.environ.get("ANTHROPIC_API_KEY"))}


def _demo_flag(demo: bool | None) -> bool:
    return FORCE_DEMO or bool(demo)


@app.post("/api/assess", response_model=Assessment)
async def assess(req: AssessRequest, demo: bool = False, ai: bool = False):
    try:
        return await run_assessment(req, demo_mode=_demo_flag(demo), ai_commentary=ai)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(status_code=502, detail=f"Assessment failed: {e}")


@app.post("/api/report.pdf")
async def report_pdf(req: AssessRequest, demo: bool = False, ai: bool = False):
    try:
        assessment = await run_assessment(req, demo_mode=_demo_flag(demo), ai_commentary=ai)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Fetch a satellite locator image (best-effort; skip in demo/offline).
    img = None
    if assessment.data_mode == "live":
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


@app.get("/")
async def index():
    idx = FRONTEND_DIR / "index.html"
    if not idx.exists():
        return JSONResponse({"detail": "frontend not found"}, status_code=404)
    return FileResponse(idx)


# Serve any other static frontend assets (app.js, css) if present.
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
