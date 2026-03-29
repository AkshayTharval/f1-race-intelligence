"""
Routers for race list and race story endpoints.
"""
import asyncio

from fastapi import APIRouter, HTTPException, Response

from backend.cache import TTL_HISTORICAL, get, set
from backend.f1_data import fastf1_data, jolpica_data, openf1_data

router = APIRouter()


@router.get("/races/{year}")
async def get_races(year: int, response: Response):
    """List all races in a season with session keys."""
    cache_key = f"races:{year}"
    cached = await get(cache_key)
    if cached:
        response.headers["X-Cache"] = "HIT"
        return cached

    races, sessions = await asyncio.gather(
        jolpica_data.get_races(year),
        openf1_data.get_sessions(year, session_type="Race"),
    )

    # Build session_key lookup by round number via circuit name matching
    session_key_map: dict[int, int] = {}
    if sessions:
        for s in sessions:
            rnd = s.get("circuit_short_name") or ""
            # Match by round_number if available
            if s.get("round_number"):
                session_key_map[int(s["round_number"])] = s["session_key"]

    result = []
    for race in races:
        round_num = int(race["round"])
        result.append(
            {
                "round": round_num,
                "name": race["raceName"],
                "circuit": race["Circuit"]["circuitName"],
                "circuit_id": race["Circuit"]["circuitId"],
                "date": race.get("date", ""),
                "country": race["Circuit"]["Location"]["country"],
                "session_key": session_key_map.get(round_num),
            }
        )

    await set(cache_key, result, TTL_HISTORICAL)
    response.headers["X-Cache"] = "MISS"
    return result


@router.get("/race/{year}/{round_num}/story")
async def get_race_story(year: int, round_num: int, response: Response):
    """Race story: lap-by-lap positions for all drivers + race events."""
    cache_key = f"story:{year}:{round_num}"
    cached = await get(cache_key)
    if cached:
        response.headers["X-Cache"] = "HIT"
        return cached

    try:
        session = fastf1_data.get_session(year, round_num, "R")
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Session not found: {e}")

    positions = fastf1_data.get_lap_positions(session)
    events = fastf1_data.get_race_events(session)
    drivers_info = fastf1_data.get_drivers_info(session)

    total_laps = max(len(v) for v in positions.values()) if positions else 0

    result = {
        "year": year,
        "round": round_num,
        "total_laps": total_laps,
        "drivers": drivers_info,
        "positions": positions,
        "events": events,
    }
    await set(cache_key, result, TTL_HISTORICAL)
    response.headers["X-Cache"] = "MISS"
    return result
