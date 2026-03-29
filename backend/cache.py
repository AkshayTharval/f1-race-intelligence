import asyncio
import json
import os
import time

import aiosqlite

TTL_LIVE = 300        # 5 minutes
TTL_HISTORICAL = 86400  # 24 hours

_DB_PATH = os.getenv("CACHE_DB_PATH", "./data/cache/f1_cache.db")
_lock = asyncio.Lock()


async def _connect() -> aiosqlite.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = await aiosqlite.connect(_DB_PATH)
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            created_at REAL NOT NULL,
            ttl INTEGER NOT NULL
        )
        """
    )
    await conn.commit()
    return conn


async def init_db() -> None:
    """Initialize the database on startup."""
    conn = await _connect()
    await conn.close()


async def get(key: str) -> dict | None:
    """Return cached value or None if missing/expired."""
    conn = await _connect()
    try:
        async with conn.execute(
            "SELECT value, created_at, ttl FROM cache WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        value, created_at, ttl = row
        if time.time() - created_at > ttl:
            return None
        return json.loads(value)
    finally:
        await conn.close()


async def set(key: str, value: dict, ttl: int) -> None:
    """Upsert a cached value with TTL."""
    async with _lock:
        conn = await _connect()
        try:
            await conn.execute(
                """
                INSERT INTO cache (key, value, created_at, ttl)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    created_at = excluded.created_at,
                    ttl = excluded.ttl
                """,
                (key, json.dumps(value), time.time(), ttl),
            )
            await conn.commit()
        finally:
            await conn.close()
