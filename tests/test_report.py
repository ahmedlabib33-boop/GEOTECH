"""Tests for the site-locator image and PDF embedding (no network)."""
import io

from backend.schemas import AssessRequest
from backend.assess import run_assessment
from backend.report.pdf import build_pdf
from backend.services.sitemap import _deg2num


def test_deg2num_known_point():
    # At zoom 0 the whole world is one tile; centre of (0,0) maps to (1,1).
    x, y = _deg2num(0.0, 0.0, 0)
    assert abs(x - 0.5) < 1e-6 and abs(y - 0.5) < 1e-6
    # Equator/prime-meridian at zoom 1 -> tile boundary (1,1).
    x, y = _deg2num(0.0, 0.0, 1)
    assert abs(x - 1.0) < 1e-6 and abs(y - 1.0) < 1e-6


def _demo():
    import asyncio
    return asyncio.run(run_assessment(AssessRequest(lat=30, lon=31, project_name="t"),
                                      demo_mode=True))


def test_pdf_without_image():
    pdf = build_pdf(_demo(), None)
    assert pdf[:4] == b"%PDF"


def test_pdf_with_image():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (256, 256), (80, 120, 90)).save(buf, format="PNG")
    pdf = build_pdf(_demo(), buf.getvalue())
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 4000
