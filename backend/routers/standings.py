"""
Standings router: championship points progression across a season.
"""
from fastapi import APIRouter, Response

from backend.cache import TTL_HISTORICAL, get, set
from backend.f1_data import jolpica_data

router = APIRouter()


@router.get("/season/{year}/standings")
async def get_season_standings(year: int, response: Response):
    """Championship points progression round by round."""
    cache_key = f"standings:{year}"
    cached = await get(cache_key)
    if cached:
        response.headers["X-Cache"] = "HIT"
        return cached

    progression = await jolpica_data.get_standings_progression(year)
    constructor_standings = await jolpica_data.get_constructor_standings(year)

    # Build a clean driver points progression:
    # [{round, race_name, date, points: {DRIVER_CODE: points}}]
    rounds_data = []
    for rnd in progression:
        points_map = {}
        for entry in rnd["standings"]:
            driver = entry.get("Driver", {})
            code = driver.get("code", driver.get("driverId", "???"))
            points_map[code] = float(entry.get("points", 0))
        rounds_data.append(
            {
                "round": rnd["round"],
                "race_name": rnd["race_name"],
                "date": rnd["date"],
                "points": points_map,
            }
        )

    # All drivers across the season
    all_drivers: dict = {}
    for rnd in progression:
        for entry in rnd["standings"]:
            driver = entry.get("Driver", {})
            code = driver.get("code", driver.get("driverId", "???"))
            if code not in all_drivers:
                all_drivers[code] = {
                    "code": code,
                    "name": f"{driver.get('givenName', '')} {driver.get('familyName', '')}".strip(),
                    "nationality": driver.get("nationality", ""),
                    "constructor": entry.get("Constructors", [{}])[-1].get("name", "")
                    if entry.get("Constructors")
                    else "",
                }

    result = {
        "year": year,
        "rounds": rounds_data,
        "drivers": list(all_drivers.values()),
        "constructor_standings": constructor_standings,
    }
    await set(cache_key, result, TTL_HISTORICAL)
    response.headers["X-Cache"] = "MISS"
    return result
