"""Compose a satellite site-locator image by stitching map tiles (no API key).

Fetches a small grid of Esri World Imagery tiles around the site, stitches them,
and draws a crosshair at the exact coordinate. Returns PNG bytes, or None on any
failure (the report then simply omits the figure).
"""
from __future__ import annotations

import asyncio
import io
import math
from typing import Optional

import httpx

TILE = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
TILE_SIZE = 256
GRID = 3            # 3x3 tiles -> 768x768 px
DEFAULT_ZOOM = 16


def _deg2num(lat: float, lon: float, z: int) -> tuple[float, float]:
    lat_r = math.radians(lat)
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n
    return x, y


async def _fetch_tile(client: httpx.AsyncClient, z: int, x: int, y: int) -> Optional[bytes]:
    n = 2 ** z
    if x < 0 or y < 0 or x >= n or y >= n:
        return None
    r = await client.get(TILE.format(z=z, x=x, y=y))
    r.raise_for_status()
    return r.content


async def site_image(lat: float, lon: float, zoom: int = DEFAULT_ZOOM) -> Optional[bytes]:
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    try:
        xc, yc = _deg2num(lat, lon, zoom)
        x0, y0 = int(math.floor(xc)) - GRID // 2, int(math.floor(yc)) - GRID // 2

        headers = {"User-Agent": "GeoTech-Satellite/1.0", "Accept": "image/*"}
        timeout = httpx.Timeout(connect=8.0, read=15.0, write=8.0, pool=8.0)
        async with httpx.AsyncClient(timeout=timeout, headers=headers,
                                     follow_redirects=True) as client:
            tasks = [_fetch_tile(client, zoom, x0 + i, y0 + j)
                     for j in range(GRID) for i in range(GRID)]
            tiles = await asyncio.gather(*tasks, return_exceptions=True)

        canvas = Image.new("RGB", (GRID * TILE_SIZE, GRID * TILE_SIZE), (20, 28, 36))
        ok = 0
        for idx, data in enumerate(tiles):
            if not isinstance(data, (bytes, bytearray)) or not data:
                continue
            i, j = idx % GRID, idx // GRID
            try:
                tile = Image.open(io.BytesIO(data)).convert("RGB")
                canvas.paste(tile, (i * TILE_SIZE, j * TILE_SIZE))
                ok += 1
            except Exception:
                continue
        if ok == 0:
            return None

        # Crosshair at the exact site pixel.
        px = int((xc - x0) * TILE_SIZE)
        py = int((yc - y0) * TILE_SIZE)
        d = ImageDraw.Draw(canvas)
        r = 11
        for off in (-1, 0, 1):                       # slight outline for contrast
            d.ellipse([px - r, py - r + off, px + r, py + r + off], outline=(255, 90, 60), width=3)
        d.line([px - r - 7, py, px + r + 7, py], fill=(255, 90, 60), width=2)
        d.line([px, py - r - 7, px, py + r + 7], fill=(255, 90, 60), width=2)

        out = io.BytesIO()
        canvas.save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return None
