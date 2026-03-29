"""
Data access layer: FastF1, OpenF1, and Jolpica API wrappers.
"""
import asyncio
import os
from datetime import datetime, timezone
from typing import Any

import fastf1
import httpx
import pandas as pd

# Enable FastF1 disk cache
_F1_CACHE_DIR = os.getenv("F1_CACHE_DIR", "./f1_cache")
os.makedirs(_F1_CACHE_DIR, exist_ok=True)
fastf1.Cache.enable_cache(_F1_CACHE_DIR)

# In-memory session cache to avoid re-loading within the same process
_session_cache: dict[tuple, Any] = {}

TYRE_COLOURS = {
    "SOFT": "#FF3333",
    "MEDIUM": "#FFF200",
    "HARD": "#FFFFFF",
    "INTERMEDIATE": "#39B54A",
    "WET": "#0067FF",
    "UNKNOWN": "#888888",
}


# ---------------------------------------------------------------------------
# FastF1 Data
# ---------------------------------------------------------------------------


class FastF1Data:
    def get_session(self, year: int, round_num: int, session_type: str = "R"):
        """Load a FastF1 session, using in-memory cache to avoid re-loading."""
        key = (year, round_num, session_type)
        if key not in _session_cache:
            session = fastf1.get_session(year, round_num, session_type)
            session.load()
            _session_cache[key] = session
        return _session_cache[key]

    def get_lap_positions(self, session) -> dict[str, list]:
        """
        Returns {driver_abbr: [position_lap1, position_lap2, ...]}
        Forward-fills NaN, sets None after last recorded lap for retired drivers.
        """
        laps = session.laps[["Driver", "LapNumber", "Position"]].copy()
        laps["Position"] = pd.to_numeric(laps["Position"], errors="coerce")
        max_lap = int(laps["LapNumber"].max())

        result = {}
        for driver, group in laps.groupby("Driver"):
            group = group.sort_values("LapNumber")
            # Forward-fill within known laps
            positions = group.set_index("LapNumber")["Position"].reindex(
                range(1, max_lap + 1)
            )
            # Forward-fill NaN
            positions = positions.ffill()
            # Find last lap the driver actually recorded
            last_lap = int(group["LapNumber"].max())
            # Set None after retirement
            positions_list = []
            for lap in range(1, max_lap + 1):
                if lap <= last_lap:
                    val = positions.get(lap)
                    positions_list.append(None if pd.isna(val) else int(val))
                else:
                    positions_list.append(None)
            result[driver] = positions_list
        return result

    def get_tyre_stints(self, session) -> list[dict]:
        """
        Returns list of {driver, compound, lap_start, lap_end, tyre_age, colour}
        """
        laps = session.laps[
            ["Driver", "LapNumber", "Compound", "TyreLife"]
        ].copy()
        stints = []
        for driver, group in laps.groupby("Driver"):
            group = group.sort_values("LapNumber").reset_index(drop=True)
            stint_start = int(group.iloc[0]["LapNumber"])
            current_compound = group.iloc[0]["Compound"]
            for i, row in group.iterrows():
                compound = row["Compound"]
                if compound != current_compound or i == len(group) - 1:
                    end_lap = int(group.iloc[i - 1]["LapNumber"]) if i > 0 else int(row["LapNumber"])
                    if i == len(group) - 1 and compound == current_compound:
                        end_lap = int(row["LapNumber"])
                    stints.append(
                        {
                            "driver": driver,
                            "compound": current_compound,
                            "lap_start": stint_start,
                            "lap_end": end_lap,
                            "tyre_age": int(group.iloc[i - 1]["TyreLife"]) if i > 0 else 0,
                            "colour": TYRE_COLOURS.get(
                                str(current_compound).upper(), "#888888"
                            ),
                        }
                    )
                    stint_start = int(row["LapNumber"])
                    current_compound = compound
        return stints

    def get_fastest_lap_telemetry(self, session, driver_abbr: str) -> dict | None:
        """
        Returns smoothed telemetry for driver's fastest lap.
        Applies rolling(3).mean() to Speed, Throttle, Brake, nGear.
        """
        try:
            driver_laps = session.laps.pick_driver(driver_abbr)
            fastest = driver_laps.pick_fastest()
            if fastest is None or fastest.empty:
                return None
            car_data = fastest.get_car_data().add_distance()
            # Smooth
            for col in ["Speed", "Throttle", "Brake", "nGear"]:
                if col in car_data.columns:
                    car_data[col] = car_data[col].rolling(3, min_periods=1).mean()
            lap_time_td = fastest["LapTime"]
            if pd.isna(lap_time_td):
                lap_time_str = "N/A"
            else:
                total_seconds = lap_time_td.total_seconds()
                minutes = int(total_seconds // 60)
                seconds = total_seconds % 60
                lap_time_str = f"{minutes}:{seconds:06.3f}"
            return {
                "driver": driver_abbr,
                "lap_number": int(fastest["LapNumber"]),
                "lap_time": lap_time_str,
                "telemetry": {
                    "distance": car_data["Distance"].tolist(),
                    "speed": car_data["Speed"].tolist(),
                    "throttle": car_data["Throttle"].tolist() if "Throttle" in car_data else [],
                    "brake": car_data["Brake"].tolist() if "Brake" in car_data else [],
                    "gear": car_data["nGear"].tolist() if "nGear" in car_data else [],
                },
            }
        except Exception:
            return None

    def get_race_events(self, session) -> list[dict]:
        """
        Parse safety car, VSC, red flag periods from session messages.
        Returns list of {lap, type, message}.
        """
        try:
            messages = session.race_control_messages
        except Exception:
            return []
        if messages is None or messages.empty:
            return []
        events = []
        laps = session.laps[["LapNumber", "Time"]].dropna()
        for _, row in messages.iterrows():
            msg = str(row.get("Message", ""))
            category = str(row.get("Category", ""))
            flag = str(row.get("Flag", ""))
            event_type = None
            if "SAFETY CAR DEPLOYED" in msg or (category == "SafetyCar" and "DEPLOYED" in msg):
                event_type = "SAFETY_CAR"
            elif "VIRTUAL SAFETY CAR" in msg and "DEPLOYED" in msg:
                event_type = "VSC"
            elif "RED FLAG" in msg or flag == "RED":
                event_type = "RED_FLAG"
            elif "SAFETY CAR IN THIS LAP" in msg or "SAFETY CAR WITHDRAWN" in msg:
                event_type = "GREEN"
            if event_type:
                # Map timestamp to nearest lap
                msg_time = row.get("Time")
                lap_num = 1
                if msg_time is not None and not laps.empty:
                    diffs = (laps["Time"] - msg_time).abs()
                    idx = diffs.idxmin()
                    lap_num = int(laps.loc[idx, "LapNumber"])
                events.append({"lap": lap_num, "type": event_type, "message": msg})
        return events

    def get_drivers_info(self, session) -> list[dict]:
        """Returns list of {abbr, name, team, colour} for all session drivers."""
        drivers = []
        for abbr in session.drivers:
            try:
                info = session.get_driver(abbr)
                try:
                    colour = fastf1.plotting.get_team_color(info["TeamName"], session)
                except Exception:
                    colour = "#888888"
                drivers.append(
                    {
                        "abbr": abbr,
                        "name": f"{info.get('FirstName', '')} {info.get('LastName', '')}".strip(),
                        "team": info.get("TeamName", ""),
                        "colour": colour,
                    }
                )
            except Exception:
                drivers.append({"abbr": abbr, "name": abbr, "team": "", "colour": "#888888"})
        return drivers


# ---------------------------------------------------------------------------
# OpenF1 API
# ---------------------------------------------------------------------------


class OpenF1Data:
    BASE_URL = "https://api.openf1.org/v1"

    async def _get(self, path: str, params: dict = None) -> list | None:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{self.BASE_URL}{path}", params=params)
                resp.raise_for_status()
                return resp.json()
        except Exception:
            return None

    async def get_sessions(self, year: int, session_type: str = None) -> list | None:
        params = {"year": year}
        if session_type:
            params["session_type"] = session_type
        return await self._get("/sessions", params)

    async def get_drivers(self, session_key: int) -> list | None:
        return await self._get("/drivers", {"session_key": session_key})

    async def get_stints(self, session_key: int) -> list | None:
        return await self._get("/stints", {"session_key": session_key})

    async def get_pit_stops(self, session_key: int) -> list | None:
        return await self._get("/pit", {"session_key": session_key})

    async def get_race_control(self, session_key: int) -> list | None:
        return await self._get("/race_control", {"session_key": session_key})

    async def get_position(self, session_key: int, driver_number: int = None) -> list | None:
        params = {"session_key": session_key}
        if driver_number:
            params["driver_number"] = driver_number
        return await self._get("/position", params)

    async def get_live_session(self) -> dict | None:
        """Return the most recent or currently active Race session."""
        sessions = await self._get("/sessions", {"session_type": "Race"})
        if not sessions:
            return None
        # Sort by date_start descending, return most recent
        sessions_sorted = sorted(
            sessions,
            key=lambda s: s.get("date_start") or "",
            reverse=True,
        )
        return sessions_sorted[0] if sessions_sorted else None

    async def get_lap_times(self, session_key: int, driver_number: int) -> list | None:
        return await self._get("/laps", {"session_key": session_key, "driver_number": driver_number})


# ---------------------------------------------------------------------------
# Jolpica (Ergast) API
# ---------------------------------------------------------------------------


class JolpicaData:
    BASE_URL = "https://api.jolpi.ca/ergast/f1"

    async def _get(self, path: str) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{self.BASE_URL}{path}?limit=100")
                resp.raise_for_status()
                return resp.json()
        except Exception:
            return None

    async def get_races(self, year: int) -> list[dict]:
        data = await self._get(f"/{year}")
        if not data:
            return []
        try:
            return data["MRData"]["RaceTable"]["Races"]
        except (KeyError, TypeError):
            return []

    async def get_results(self, year: int, round_num: int) -> list[dict]:
        data = await self._get(f"/{year}/{round_num}/results")
        if not data:
            return []
        try:
            races = data["MRData"]["RaceTable"]["Races"]
            return races[0]["Results"] if races else []
        except (KeyError, TypeError, IndexError):
            return []

    async def get_standings_after_round(self, year: int, round_num: int) -> list[dict]:
        data = await self._get(f"/{year}/{round_num}/driverStandings")
        if not data:
            return []
        try:
            lists = data["MRData"]["StandingsTable"]["StandingsLists"]
            return lists[0]["DriverStandings"] if lists else []
        except (KeyError, TypeError, IndexError):
            return []

    async def get_standings_progression(self, year: int) -> list[dict]:
        """Fetch cumulative standings after every round. Returns [{round, race_name, standings: [...]}]"""
        races = await self.get_races(year)
        if not races:
            return []
        semaphore = asyncio.Semaphore(4)

        async def fetch_round(race: dict) -> dict:
            round_num = int(race["round"])
            async with semaphore:
                standings = await self.get_standings_after_round(year, round_num)
            return {
                "round": round_num,
                "race_name": race["raceName"],
                "date": race.get("date", ""),
                "standings": standings,
            }

        results = await asyncio.gather(*[fetch_round(r) for r in races])
        return sorted(results, key=lambda x: x["round"])

    async def get_constructor_standings(self, year: int) -> list[dict]:
        data = await self._get(f"/{year}/constructorStandings")
        if not data:
            return []
        try:
            lists = data["MRData"]["StandingsTable"]["StandingsLists"]
            return lists[0]["ConstructorStandings"] if lists else []
        except (KeyError, TypeError, IndexError):
            return []


# Module-level singletons
fastf1_data = FastF1Data()
openf1_data = OpenF1Data()
jolpica_data = JolpicaData()
