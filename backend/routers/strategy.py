"""
Strategy router: pit stop timeline, tyre strategy, undercut/overcut detector.
"""
import asyncio

from fastapi import APIRouter, HTTPException, Response

from backend.cache import TTL_HISTORICAL, get, set
from backend.f1_data import TYRE_COLOURS, fastf1_data, openf1_data

router = APIRouter()


def _detect_undercut(
    driver: str,
    pit_lap: int,
    lap_times: dict[str, dict[int, float]],
    positions_before: dict[str, int],
    positions_after: dict[str, int],
) -> tuple[str, str]:
    """
    Classify a pit stop as undercut/overcut/neutral.
    Returns (label, explanation).
    """
    pos_before = positions_before.get(driver, 99)
    pos_after = positions_after.get(driver, 99)

    # Find nearest competitor (within 3 positions before the pit)
    nearby = [
        (d, p)
        for d, p in positions_before.items()
        if d != driver and abs(p - pos_before) <= 3
    ]

    if not nearby:
        return "Neutral", "No nearby competitors to compare."

    # Compare pace in laps after pit vs competitors who hadn't pitted yet
    driver_post_laps = {
        l: t for l, t in lap_times.get(driver, {}).items() if l in range(pit_lap + 1, pit_lap + 4)
    }

    for comp, comp_pos_before in nearby:
        comp_pos_after = positions_after.get(comp, 99)
        comp_post_laps = {
            l: t for l, t in lap_times.get(comp, {}).items() if l in range(pit_lap, pit_lap + 3)
        }
        if not driver_post_laps or not comp_post_laps:
            continue

        avg_driver = sum(driver_post_laps.values()) / len(driver_post_laps)
        avg_comp = sum(comp_post_laps.values()) / len(comp_post_laps)

        # Undercut: driver pitted, emerged ahead, and was faster on fresh tyres
        if pos_before > pos_after and avg_driver < avg_comp:
            return (
                "Undercut Success",
                f"{driver} pitted on lap {pit_lap}, gained fresher tyres and jumped {comp}.",
            )
        elif pos_before > pos_after:
            return (
                "Overcut Success",
                f"{driver} gained position via strategic timing vs {comp}.",
            )
        elif comp_pos_before > comp_pos_after and avg_comp < avg_driver:
            return (
                "Undercut Failed",
                f"{driver} pitted on lap {pit_lap} but {comp} maintained position.",
            )

    if pos_before < pos_after:
        return "Neutral", f"{driver} pitted on lap {pit_lap} with no net position change."
    return "Neutral", f"{driver} pitted on lap {pit_lap} — no strategic impact detected."


@router.get("/race/{year}/{round_num}/strategy")
async def get_race_strategy(year: int, round_num: int, response: Response):
    """Pit stop timeline with tyre colours and undercut/overcut detection."""
    cache_key = f"strategy:{year}:{round_num}"
    cached = await get(cache_key)
    if cached:
        response.headers["X-Cache"] = "HIT"
        return cached

    # Get session for FastF1 data
    try:
        session = fastf1_data.get_session(year, round_num, "R")
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Session not found: {e}")

    stints = fastf1_data.get_tyre_stints(session)
    drivers_info = fastf1_data.get_drivers_info(session)

    # Build lap times dict: {driver: {lap: seconds}}
    laps_df = session.laps[["Driver", "LapNumber", "LapTime", "Position"]].copy()
    lap_times: dict = {}
    for driver, group in laps_df.groupby("Driver"):
        lap_times[driver] = {}
        for _, row in group.iterrows():
            lt = row["LapTime"]
            if lt is not None and not hasattr(lt, '__class__') or not hasattr(lt, 'total_seconds'):
                continue
            try:
                lap_times[driver][int(row["LapNumber"])] = lt.total_seconds()
            except Exception:
                pass

    # Build pit stops from FastF1 laps (compound changes)
    pit_stops = []
    for driver, group in laps_df.groupby("Driver"):
        group = group.sort_values("LapNumber").reset_index(drop=True)
        # Pit stop = compound change or TyreLife reset
        prev_compound = None
        for _, row in session.laps[session.laps["Driver"] == driver].sort_values("LapNumber").iterrows():
            compound = row.get("Compound", "UNKNOWN")
            lap = int(row["LapNumber"])
            if prev_compound is not None and compound != prev_compound:
                # Position before and after pit
                pre_lap_pos = group[group["LapNumber"] == lap - 1]["Position"].values
                post_lap_pos = group[group["LapNumber"] == lap]["Position"].values
                pos_before = {driver: int(pre_lap_pos[0])} if len(pre_lap_pos) else {}
                pos_after = {driver: int(post_lap_pos[0])} if len(post_lap_pos) else {}

                # Enrich with all drivers' positions
                for _, r2 in group.iterrows():
                    if int(r2["LapNumber"]) == lap - 1 and r2["Driver"] != driver:
                        p = r2["Position"]
                        if not hasattr(p, '__float__') or p != p:
                            continue
                        pos_before[r2["Driver"]] = int(p)
                    if int(r2["LapNumber"]) == lap and r2["Driver"] != driver:
                        p = r2["Position"]
                        if not hasattr(p, '__float__') or p != p:
                            continue
                        pos_after[r2["Driver"]] = int(p)

                # For positions, use all drivers
                all_pos_before: dict = {}
                all_pos_after: dict = {}
                for _, row2 in laps_df.iterrows():
                    ln = int(row2["LapNumber"])
                    d2 = row2["Driver"]
                    p2 = row2["Position"]
                    try:
                        p2_int = int(p2)
                    except Exception:
                        continue
                    if ln == lap - 1:
                        all_pos_before[d2] = p2_int
                    elif ln == lap:
                        all_pos_after[d2] = p2_int

                label, explanation = _detect_undercut(
                    driver, lap, lap_times, all_pos_before, all_pos_after
                )
                pit_stops.append(
                    {
                        "driver": driver,
                        "lap": lap,
                        "compound_before": prev_compound,
                        "compound_after": compound,
                        "label": label,
                        "explanation": explanation,
                    }
                )
            prev_compound = compound

    result = {
        "year": year,
        "round": round_num,
        "stints": stints,
        "pit_stops": pit_stops,
        "drivers": drivers_info,
        "tyre_colours": TYRE_COLOURS,
    }
    await set(cache_key, result, TTL_HISTORICAL)
    response.headers["X-Cache"] = "MISS"
    return result
