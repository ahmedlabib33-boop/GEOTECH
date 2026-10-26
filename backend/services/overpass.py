"""Shared OpenStreetMap Overpass access with endpoint failover.

The public Overpass instances vary in availability and some block cloud/
datacenter IP ranges, so a single hard-coded endpoint is fragile from a
serverless host. This tries several mirrors in turn (first success wins),
remembers the last endpoint that worked so later calls hit it first, and logs
each failure to stderr for observability. Callers get the parsed element list
or an exception (real-only: a total failure degrades to 'unavailable').
"""
from __future__ import annotations

import sys

import httpx

# Mirrors with full planet data, tried in order (first success wins).
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

_last_good: dict[str, str | None] = {"url": None}


async def overpass_elements(client: httpx.AsyncClient, query: str,
                            read: float = 5.0) -> list:
    """POST an Overpass QL query, failing over across mirrors. Returns the
    `elements` list from the first endpoint that answers 200. Timeouts are kept
    short so a flaky/overloaded instance fails fast; the caller bounds the total
    so Overpass trouble can never stall the whole assessment (real-only)."""
    timeout = httpx.Timeout(connect=4.0, read=read, write=10.0, pool=10.0)
    order = ENDPOINTS
    if _last_good["url"] in ENDPOINTS:
        order = [_last_good["url"]] + [u for u in ENDPOINTS if u != _last_good["url"]]

    last_exc: Exception | None = None
    for url in order:
        try:
            r = await client.post(url, data={"data": query}, timeout=timeout)
            r.raise_for_status()
            elements = r.json().get("elements", [])
            _last_good["url"] = url
            return elements
        except Exception as e:  # noqa: BLE001 - try the next mirror
            last_exc = e
            print(f"[overpass] {url} failed: {type(e).__name__}: {e}", file=sys.stderr)
    raise last_exc or RuntimeError("Overpass: all endpoints failed")
