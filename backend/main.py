"""
F1 Race Intelligence Dashboard — FastAPI Backend
"""
import asyncio
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.cache import init_db
from backend.routers import live, races, standings, strategy, telemetry

app = FastAPI(
    title="F1 Race Intelligence API",
    description="Formula 1 data API powering the Race Intelligence Dashboard. "
    "Serves lap data, telemetry, strategy analysis, and live timing from FastF1, OpenF1, and Jolpica.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(races.router, tags=["Races"])
app.include_router(strategy.router, tags=["Strategy"])
app.include_router(telemetry.router, tags=["Telemetry"])
app.include_router(standings.router, tags=["Standings"])
app.include_router(live.router, tags=["Live"])


@app.on_event("startup")
async def startup_event():
    # Initialize SQLite cache
    await init_db()

    # Ensure FastF1 cache directory exists
    f1_cache_dir = os.getenv("F1_CACHE_DIR", "./f1_cache")
    os.makedirs(f1_cache_dir, exist_ok=True)

    # Pre-warm: load 2024 Bahrain GP in background so first request is fast
    async def prewarm():
        try:
            from backend.f1_data import fastf1_data
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, fastf1_data.get_session, 2024, 1, "R")
        except Exception:
            pass  # Pre-warm failure is non-fatal

    asyncio.create_task(prewarm())


@app.get("/", tags=["Health"])
async def root():
    return {
        "status": "ok",
        "service": "F1 Race Intelligence API",
        "docs": "/docs",
        "endpoints": [
            "GET /races/{year}",
            "GET /race/{year}/{round}/story",
            "GET /race/{year}/{round}/strategy",
            "GET /race/{year}/{round}/telemetry/{driver}",
            "GET /season/{year}/standings",
            "GET /live/session",
        ],
    }
