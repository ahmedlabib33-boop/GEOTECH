"""Shared async HTTP client with sane timeouts and a friendly User-Agent.

Public data APIs (Nominatim in particular) require a descriptive User-Agent and
are rate limited, so a single shared client keeps us polite and efficient.
"""
from __future__ import annotations

import httpx

USER_AGENT = "GeoTech-Satellite-Assessment/1.0 (open geospatial desk study tool)"

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)


def new_client() -> httpx.AsyncClient:
    """Create a configured AsyncClient. Caller is responsible for closing it."""
    return httpx.AsyncClient(
        timeout=_DEFAULT_TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        follow_redirects=True,
    )
