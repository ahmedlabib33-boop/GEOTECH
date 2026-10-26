"""Tests for the in-process TTL data cache (reliability layer)."""
import pytest

from backend.services import cache


@pytest.fixture(autouse=True)
def _clear():
    cache.clear()
    yield
    cache.clear()


async def _make(value, counter):
    counter["n"] += 1
    return value


def test_caches_usable_result_once():
    import asyncio
    counter = {"n": 0}

    async def run():
        a = await cache.cached("x", 1.0, 2.0, lambda: _make("good", counter), usable=lambda v: True)
        b = await cache.cached("x", 1.0, 2.0, lambda: _make("good", counter), usable=lambda v: True)
        return a, b

    a, b = asyncio.run(run())
    assert a == b == "good"
    assert counter["n"] == 1          # second call served from cache


def test_does_not_cache_unusable_result():
    import asyncio
    counter = {"n": 0}

    async def run():
        await cache.cached("y", 1.0, 2.0, lambda: _make(None, counter), usable=lambda v: v is not None)
        await cache.cached("y", 1.0, 2.0, lambda: _make(None, counter), usable=lambda v: v is not None)

    asyncio.run(run())
    assert counter["n"] == 2          # failure never cached -> recomputed


def test_rounds_coordinates_to_same_bucket():
    import asyncio
    counter = {"n": 0}

    async def run():
        await cache.cached("z", 1.00001, 2.00001, lambda: _make("v", counter), usable=lambda v: True)
        # within ~110 m -> same rounded key -> cache hit
        await cache.cached("z", 1.00002, 2.00002, lambda: _make("v", counter), usable=lambda v: True)

    asyncio.run(run())
    assert counter["n"] == 1


def test_clear_empties_store():
    import asyncio
    counter = {"n": 0}

    async def run():
        await cache.cached("w", 5.0, 6.0, lambda: _make("v", counter), usable=lambda v: True)
        cache.clear()
        await cache.cached("w", 5.0, 6.0, lambda: _make("v", counter), usable=lambda v: True)

    asyncio.run(run())
    assert counter["n"] == 2
