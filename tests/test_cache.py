"""
Unit tests for backend/cache.py — TTL-based async SQLite cache.
"""
import time

import pytest

import backend.cache as cache_mod
from backend.cache import TTL_HISTORICAL, TTL_LIVE


# ---------------------------------------------------------------------------
# TTL constant sanity checks
# ---------------------------------------------------------------------------


def test_ttl_live_is_5_minutes():
    assert TTL_LIVE == 300


def test_ttl_historical_is_24_hours():
    assert TTL_HISTORICAL == 86400


# ---------------------------------------------------------------------------
# Cache get/set round-trips
# ---------------------------------------------------------------------------


async def test_get_missing_key_returns_none(tmp_db):
    result = await cache_mod.get("nonexistent_key")
    assert result is None


async def test_set_and_get_returns_value(tmp_db):
    await cache_mod.set("k1", {"answer": 42}, ttl=3600)
    result = await cache_mod.get("k1")
    assert result == {"answer": 42}


async def test_set_and_get_nested_structure(tmp_db):
    payload = {"drivers": ["VER", "HAM"], "laps": [1, 2, 3], "meta": {"year": 2024}}
    await cache_mod.set("k2", payload, ttl=3600)
    result = await cache_mod.get("k2")
    assert result == payload


async def test_upsert_overwrites_previous_value(tmp_db):
    await cache_mod.set("k3", {"v": 1}, ttl=3600)
    await cache_mod.set("k3", {"v": 2}, ttl=3600)
    result = await cache_mod.get("k3")
    assert result == {"v": 2}


# ---------------------------------------------------------------------------
# TTL expiry
# ---------------------------------------------------------------------------


class _MockTime:
    """Replaces the `time` module in cache.py to simulate clock advancement."""

    def __init__(self, offset: float = 0.0):
        self._offset = offset

    def time(self) -> float:
        return time.time() + self._offset


async def test_get_expired_entry_returns_none(monkeypatch, tmp_db):
    await cache_mod.set("expiring", {"data": "stale"}, ttl=5)

    # Advance the clock by 10 seconds inside cache.py
    monkeypatch.setattr(cache_mod, "time", _MockTime(offset=10.0))

    result = await cache_mod.get("expiring")
    assert result is None


async def test_get_not_yet_expired_returns_value(monkeypatch, tmp_db):
    await cache_mod.set("fresh", {"data": "current"}, ttl=3600)

    # Advance clock by only 60 seconds — still well within TTL
    monkeypatch.setattr(cache_mod, "time", _MockTime(offset=60.0))

    result = await cache_mod.get("fresh")
    assert result == {"data": "current"}


# ---------------------------------------------------------------------------
# Concurrent writes (asyncio lock)
# ---------------------------------------------------------------------------


async def test_multiple_sequential_writes_do_not_corrupt(tmp_db):
    """Multiple writes to different keys all produce readable values."""
    for i in range(10):
        await cache_mod.set(f"key_{i}", {"i": i}, ttl=3600)

    for i in range(10):
        result = await cache_mod.get(f"key_{i}")
        assert result == {"i": i}


# ---------------------------------------------------------------------------
# init_db is idempotent
# ---------------------------------------------------------------------------


async def test_init_db_idempotent(tmp_db):
    """Calling init_db twice must not raise and leave DB usable."""
    await cache_mod.init_db()
    await cache_mod.init_db()
    await cache_mod.set("after_init", {"ok": True}, ttl=3600)
    result = await cache_mod.get("after_init")
    assert result == {"ok": True}
