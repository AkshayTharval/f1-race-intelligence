"""
Live race router: current or most recent session data.
"""
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Response

from backend.cache import TTL_LIVE, get, set
from backend.f1_data import openf1_data

router = APIRouter()


def _is_session_live(session: dict) -> bool:
    """Return True if the session is currently ongoing."""
    date_end = session.get("date_end")
    if date_end is None:
        return True
    try:
        end_dt = datetime.fromisoformat(date_end.replace("Z", "+00:00"))
        return end_dt > datetime.now(timezone.utc)
    except Exception:
        return False


@router.get("/live/session")
async def get_live_session(response: Response):
    """Current or most recent race session with live timing data."""
    cache_key = "live:session"
    cached = await get(cache_key)
    if cached:
        response.headers["X-Cache"] = "HIT"
        return cached

    session = await openf1_data.get_live_session()
    if not session:
        result = {"is_live": False, "session_key": None, "drivers": [], "error": "No sessions found"}
        await set(cache_key, result, TTL_LIVE)
        response.headers["X-Cache"] = "MISS"
        return result

    session_key = session.get("session_key")
    is_live = _is_session_live(session)

    # Fetch drivers and latest positions concurrently
    drivers_raw, positions_raw = await asyncio.gather(
        openf1_data.get_drivers(session_key),
        openf1_data.get_position(session_key),
    )

    # Build latest position per driver (last entry in position stream)
    latest_positions: dict[int, int] = {}
    if positions_raw:
        for p in positions_raw:
            dn = p.get("driver_number")
            pos = p.get("position")
            if dn and pos:
                latest_positions[dn] = pos

    # Get latest stints for tyre info
    stints_raw = await openf1_data.get_stints(session_key) or []
    latest_stints: dict[int, dict] = {}
    for s in stints_raw:
        dn = s.get("driver_number")
        if dn:
            # Last stint wins (highest stint_number)
            if dn not in latest_stints or s.get("stint_number", 0) > latest_stints[dn].get("stint_number", 0):
                latest_stints[dn] = s

    # Build driver list sorted by position
    drivers = []
    if drivers_raw:
        for d in drivers_raw:
            dn = d.get("driver_number")
            pos = latest_positions.get(dn, 99)
            stint = latest_stints.get(dn, {})
            team_colour = d.get("team_colour", "888888")
            if not team_colour.startswith("#"):
                team_colour = f"#{team_colour}"
            drivers.append(
                {
                    "driver_number": dn,
                    "abbr": d.get("name_acronym", "???"),
                    "name": d.get("full_name", ""),
                    "team": d.get("team_name", ""),
                    "colour": team_colour,
                    "position": pos,
                    "compound": stint.get("compound", "UNKNOWN"),
                    "tyre_age": stint.get("tyre_age_at_start", 0),
                    "headshot_url": d.get("headshot_url", ""),
                }
            )
    drivers.sort(key=lambda x: x["position"])

    result = {
        "is_live": is_live,
        "session_key": session_key,
        "session_name": session.get("session_name", "Race"),
        "circuit": session.get("circuit_short_name", ""),
        "location": session.get("location", ""),
        "country": session.get("country_name", ""),
        "year": session.get("year"),
        "date_start": session.get("date_start", ""),
        "drivers": drivers,
    }
    await set(cache_key, result, TTL_LIVE)
    response.headers["X-Cache"] = "MISS"
    return result
