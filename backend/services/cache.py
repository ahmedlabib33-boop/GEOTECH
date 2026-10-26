"""Tiny in-process TTL cache for lat/lon data fetches.

Vercel keeps a Lambda warm between requests, so caching the slow, stable
geophysical lookups (soil, terrain, climate, seismic, vegetation, wind/snow)
by rounded coordinate makes repeat and nearby assessments fast and shields them
from transient upstream blips.

Only a *usable* result is cached (never a failure or an 'unavailable'
placeholder), so a source that was briefly down is retried on the next request
rather than being pinned to a bad value for the whole TTL.
"""
from __future__ import annotations

import time
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")

_STORE: dict[str, tuple[float, object]] = {}
DEFAULT_TTL = 21_600.0  # 6 hours — geophysical data barely changes


def _key(name: str, lat: float, lon: float) -> str:
    # ~110 m granularity: nearby points reuse the same cached lookup.
    return f"{name}:{round(lat, 3)}:{round(lon, 3)}"


async def cached(name: str, lat: float, lon: float,
                 factory: Callable[[], Awaitable[T]],
                 usable: Callable[[T], bool],
                 ttl: float = DEFAULT_TTL) -> T:
    """Return a cached usable result for (name, lat, lon) or compute it.

    `factory()` produces the awaitable that fetches the value; if it raises, the
    error propagates and nothing is cached. The result is stored only when
    `usable(result)` is true, so failures are never cached.
    """
    key = _key(name, lat, lon)
    hit = _STORE.get(key)
    if hit is not None and (time.time() - hit[0]) < ttl:
        return hit[1]  # type: ignore[return-value]
    value = await factory()
    try:
        ok = usable(value)
    except Exception:
        ok = False
    if ok:
        _STORE[key] = (time.time(), value)
    return value


def clear() -> None:
    """Drop everything (used by the test suite for isolation)."""
    _STORE.clear()
