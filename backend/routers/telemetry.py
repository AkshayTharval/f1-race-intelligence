"""
Telemetry router: fastest lap telemetry overlay per driver.
"""
from fastapi import APIRouter, HTTPException, Response

from backend.cache import TTL_HISTORICAL, get, set
from backend.f1_data import fastf1_data

router = APIRouter()


@router.get("/race/{year}/{round_num}/telemetry/{driver}")
async def get_telemetry(year: int, round_num: int, driver: str, response: Response):
    """Return smoothed fastest-lap telemetry (speed, throttle, brake, gear) for a driver."""
    driver = driver.upper()
    cache_key = f"telemetry:{year}:{round_num}:{driver}"
    cached = await get(cache_key)
    if cached:
        response.headers["X-Cache"] = "HIT"
        return cached

    try:
        session = fastf1_data.get_session(year, round_num, "R")
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Session not found: {e}")

    result = fastf1_data.get_fastest_lap_telemetry(session, driver)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No telemetry for driver {driver}")

    await set(cache_key, result, TTL_HISTORICAL)
    response.headers["X-Cache"] = "MISS"
    return result
