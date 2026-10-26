"""Shared async HTTP client with sane timeouts, a friendly User-Agent, and a
retry helper.

Public data APIs (Nominatim in particular) require a descriptive User-Agent and
are rate limited, so a single shared client keeps us polite and efficient. The
`with_retry` helper retries transient failures (timeouts, transport errors, 5xx)
with exponential backoff so one blip does not drop a whole data layer.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar

import httpx

USER_AGENT = "GeoTech-Satellite-Assessment/1.0 (open geospatial desk study tool)"

# Read timeout kept modest so two attempts stay within the 60 s function budget.
_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=10.0)

T = TypeVar("T")


def new_client() -> httpx.AsyncClient:
    """Create a configured AsyncClient. Caller is responsible for closing it."""
    return httpx.AsyncClient(
        timeout=_DEFAULT_TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        follow_redirects=True,
    )


async def with_retry(factory: Callable[[], Awaitable[T]], attempts: int = 2,
                     base_delay: float = 0.5) -> T:
    """Await `factory()`, retrying transient failures with exponential backoff.

    Retries on timeouts, transport errors and HTTP 5xx; a 4xx (e.g. bad request,
    not found) is raised immediately. `factory` must return a fresh awaitable on
    each call.
    """
    last: Exception | None = None
    for i in range(attempts):
        try:
            return await factory()
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last = e
        except httpx.HTTPStatusError as e:
            code = e.response.status_code if e.response is not None else 0
            if not (500 <= code < 600):
                raise
            last = e
        if i < attempts - 1:
            await asyncio.sleep(base_delay * (2 ** i))
    assert last is not None
    raise last
