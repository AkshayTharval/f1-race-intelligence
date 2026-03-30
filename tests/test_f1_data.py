"""
Unit tests for backend/f1_data.py — data processing logic.

FastF1 sessions are mocked with pandas DataFrames so no network or disk
access is required. OpenF1 and Jolpica tests mock the HTTP _get() helper.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from backend.f1_data import (
    TYRE_COLOURS,
    FastF1Data,
    JolpicaData,
    OpenF1Data,
)

f1 = FastF1Data()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_laps(rows: list) -> MagicMock:
    """Return a mock session whose .laps attribute is a DataFrame built from rows."""
    session = MagicMock()
    session.laps = pd.DataFrame(rows)
    return session


# ---------------------------------------------------------------------------
# TYRE_COLOURS
# ---------------------------------------------------------------------------


def test_tyre_colours_soft():
    assert TYRE_COLOURS["SOFT"] == "#FF3333"


def test_tyre_colours_medium():
    assert TYRE_COLOURS["MEDIUM"] == "#FFF200"


def test_tyre_colours_hard():
    assert TYRE_COLOURS["HARD"] == "#FFFFFF"


def test_tyre_colours_intermediate():
    assert TYRE_COLOURS["INTERMEDIATE"] == "#39B54A"


def test_tyre_colours_wet():
    assert TYRE_COLOURS["WET"] == "#0067FF"


# ---------------------------------------------------------------------------
# get_lap_positions
# ---------------------------------------------------------------------------


def test_get_lap_positions_basic():
    session = _make_laps([
        {"Driver": "VER", "LapNumber": 1, "Position": 1.0},
        {"Driver": "VER", "LapNumber": 2, "Position": 2.0},
        {"Driver": "HAM", "LapNumber": 1, "Position": 2.0},
        {"Driver": "HAM", "LapNumber": 2, "Position": 1.0},
    ])
    result = f1.get_lap_positions(session)
    assert result["VER"] == [1, 2]
    assert result["HAM"] == [2, 1]


def test_get_lap_positions_retired_driver_gets_none_after_last_lap():
    """HAM retires after lap 2; lap 3 entry must be None."""
    session = _make_laps([
        {"Driver": "VER", "LapNumber": 1, "Position": 1.0},
        {"Driver": "VER", "LapNumber": 2, "Position": 1.0},
        {"Driver": "VER", "LapNumber": 3, "Position": 1.0},
        {"Driver": "HAM", "LapNumber": 1, "Position": 2.0},
        {"Driver": "HAM", "LapNumber": 2, "Position": 2.0},
        # HAM has no lap 3 row — treated as retired
    ])
    result = f1.get_lap_positions(session)
    assert result["VER"] == [1, 1, 1]
    assert result["HAM"] == [2, 2, None]


def test_get_lap_positions_nan_forward_filled():
    """NaN positions within known laps are forward-filled from the previous lap."""
    session = _make_laps([
        {"Driver": "VER", "LapNumber": 1, "Position": 3.0},
        {"Driver": "VER", "LapNumber": 2, "Position": float("nan")},
        {"Driver": "VER", "LapNumber": 3, "Position": 2.0},
    ])
    result = f1.get_lap_positions(session)
    # Lap 2 was NaN → forward-filled to 3 (from lap 1)
    assert result["VER"][1] == 3


def test_get_lap_positions_single_driver_single_lap():
    session = _make_laps([
        {"Driver": "VER", "LapNumber": 1, "Position": 5.0},
    ])
    result = f1.get_lap_positions(session)
    assert result["VER"] == [5]


# ---------------------------------------------------------------------------
# get_tyre_stints
# ---------------------------------------------------------------------------


def _make_stints_session(rows: list) -> MagicMock:
    session = MagicMock()
    df = pd.DataFrame(rows)
    session.laps = df
    return session


def test_get_tyre_stints_single_compound():
    session = _make_stints_session([
        {"Driver": "VER", "LapNumber": 1, "Compound": "MEDIUM", "TyreLife": 1},
        {"Driver": "VER", "LapNumber": 2, "Compound": "MEDIUM", "TyreLife": 2},
        {"Driver": "VER", "LapNumber": 3, "Compound": "MEDIUM", "TyreLife": 3},
    ])
    result = f1.get_tyre_stints(session)
    assert len(result) == 1
    assert result[0]["compound"] == "MEDIUM"
    assert result[0]["lap_start"] == 1
    assert result[0]["lap_end"] == 3
    assert result[0]["colour"] == TYRE_COLOURS["MEDIUM"]


def test_get_tyre_stints_two_compounds():
    session = _make_stints_session([
        {"Driver": "VER", "LapNumber": 1, "Compound": "MEDIUM", "TyreLife": 1},
        {"Driver": "VER", "LapNumber": 2, "Compound": "MEDIUM", "TyreLife": 2},
        {"Driver": "VER", "LapNumber": 3, "Compound": "SOFT", "TyreLife": 1},
        {"Driver": "VER", "LapNumber": 4, "Compound": "SOFT", "TyreLife": 2},
    ])
    result = f1.get_tyre_stints(session)
    assert len(result) == 2
    assert result[0]["compound"] == "MEDIUM"
    assert result[0]["lap_start"] == 1
    assert result[0]["lap_end"] == 2
    assert result[1]["compound"] == "SOFT"
    assert result[1]["lap_start"] == 3
    assert result[1]["lap_end"] == 4


def test_get_tyre_stints_colours_all_compounds():
    """Each compound maps to its official hex colour.

    Add an extra lap on each compound so the final stint's compound change is
    never on the very last row — this ensures the WET stint is fully appended.
    """
    session = _make_stints_session([
        {"Driver": "VER", "LapNumber": 1, "Compound": "SOFT", "TyreLife": 1},
        {"Driver": "VER", "LapNumber": 2, "Compound": "SOFT", "TyreLife": 2},
        {"Driver": "VER", "LapNumber": 3, "Compound": "MEDIUM", "TyreLife": 1},
        {"Driver": "VER", "LapNumber": 4, "Compound": "HARD", "TyreLife": 1},
        {"Driver": "VER", "LapNumber": 5, "Compound": "INTERMEDIATE", "TyreLife": 1},
        {"Driver": "VER", "LapNumber": 6, "Compound": "WET", "TyreLife": 1},
        {"Driver": "VER", "LapNumber": 7, "Compound": "WET", "TyreLife": 2},
    ])
    result = f1.get_tyre_stints(session)
    colour_map = {s["compound"]: s["colour"] for s in result}
    assert colour_map["SOFT"] == "#FF3333"
    assert colour_map["MEDIUM"] == "#FFF200"
    assert colour_map["HARD"] == "#FFFFFF"
    assert colour_map["INTERMEDIATE"] == "#39B54A"
    assert colour_map["WET"] == "#0067FF"


def test_get_tyre_stints_two_drivers_independent():
    """Stints for different drivers are tracked independently."""
    session = _make_stints_session([
        {"Driver": "VER", "LapNumber": 1, "Compound": "MEDIUM", "TyreLife": 1},
        {"Driver": "VER", "LapNumber": 2, "Compound": "MEDIUM", "TyreLife": 2},
        {"Driver": "HAM", "LapNumber": 1, "Compound": "SOFT", "TyreLife": 1},
        {"Driver": "HAM", "LapNumber": 2, "Compound": "SOFT", "TyreLife": 2},
    ])
    result = f1.get_tyre_stints(session)
    ver_stints = [s for s in result if s["driver"] == "VER"]
    ham_stints = [s for s in result if s["driver"] == "HAM"]
    assert len(ver_stints) == 1
    assert ver_stints[0]["compound"] == "MEDIUM"
    assert len(ham_stints) == 1
    assert ham_stints[0]["compound"] == "SOFT"


# ---------------------------------------------------------------------------
# get_race_events
# ---------------------------------------------------------------------------


def _make_events_session(rows: list) -> MagicMock:
    session = MagicMock()
    session.race_control_messages = pd.DataFrame(rows)
    return session


def test_get_race_events_vsc_deployed():
    session = _make_events_session([
        {"Message": "VIRTUAL SAFETY CAR DEPLOYED", "Category": "SafetyCar", "Flag": "", "Lap": 10},
    ])
    result = f1.get_race_events(session)
    assert len(result) == 1
    assert result[0]["type"] == "VSC"
    assert result[0]["lap"] == 10


def test_get_race_events_vsc_ending():
    session = _make_events_session([
        {"Message": "VIRTUAL SAFETY CAR ENDING", "Category": "SafetyCar", "Flag": "", "Lap": 12},
    ])
    result = f1.get_race_events(session)
    assert len(result) == 1
    assert result[0]["type"] == "VSC_END"


def test_get_race_events_safety_car_deployed():
    session = _make_events_session([
        {"Message": "SAFETY CAR DEPLOYED", "Category": "SafetyCar", "Flag": "", "Lap": 5},
    ])
    result = f1.get_race_events(session)
    assert len(result) == 1
    assert result[0]["type"] == "SAFETY_CAR"


def test_get_race_events_safety_car_in_this_lap():
    session = _make_events_session([
        {"Message": "SAFETY CAR IN THIS LAP", "Category": "SafetyCar", "Flag": "", "Lap": 8},
    ])
    result = f1.get_race_events(session)
    assert len(result) == 1
    assert result[0]["type"] == "SC_END"


def test_get_race_events_red_flag():
    session = _make_events_session([
        {"Message": "RED FLAG", "Category": "", "Flag": "RED", "Lap": 35},
    ])
    result = f1.get_race_events(session)
    assert len(result) == 1
    assert result[0]["type"] == "RED_FLAG"


def test_get_race_events_skips_chequered():
    session = _make_events_session([
        {"Message": "CHEQUERED FLAG", "Category": "", "Flag": "", "Lap": 70},
    ])
    result = f1.get_race_events(session)
    assert len(result) == 0


def test_get_race_events_skips_yellow_flag():
    session = _make_events_session([
        {"Message": "YELLOW FLAG SECTOR 3", "Category": "", "Flag": "YELLOW", "Lap": 20},
    ])
    result = f1.get_race_events(session)
    assert len(result) == 0


def test_get_race_events_skips_blue_flag():
    session = _make_events_session([
        {"Message": "BLUE FLAG FOR CAR 44", "Category": "", "Flag": "BLUE", "Lap": 30},
    ])
    result = f1.get_race_events(session)
    assert len(result) == 0


def test_get_race_events_skips_clear():
    session = _make_events_session([
        {"Message": "TRACK CLEAR", "Category": "", "Flag": "CLEAR", "Lap": 40},
    ])
    result = f1.get_race_events(session)
    assert len(result) == 0


def test_get_race_events_empty_messages():
    session = MagicMock()
    session.race_control_messages = pd.DataFrame()
    result = f1.get_race_events(session)
    assert result == []


def test_get_race_events_exception_returns_empty():
    """If race_control_messages raises, return []."""
    session = MagicMock()
    type(session).race_control_messages = property(
        fget=lambda self: (_ for _ in ()).throw(Exception("no data"))
    )
    result = f1.get_race_events(session)
    assert result == []


def test_get_race_events_mixed_messages():
    session = _make_events_session([
        {"Message": "VIRTUAL SAFETY CAR DEPLOYED", "Category": "SafetyCar", "Flag": "", "Lap": 10},
        {"Message": "CHEQUERED FLAG", "Category": "", "Flag": "", "Lap": 70},
        {"Message": "RED FLAG", "Category": "", "Flag": "RED", "Lap": 35},
    ])
    result = f1.get_race_events(session)
    assert len(result) == 2
    types = {e["type"] for e in result}
    assert "VSC" in types
    assert "RED_FLAG" in types


# ---------------------------------------------------------------------------
# get_drivers_info
# ---------------------------------------------------------------------------


def _make_drivers_session(driver_map: dict) -> MagicMock:
    """
    driver_map: {driver_number: info_dict}
    e.g. {"44": {"Abbreviation": "HAM", "TeamName": "Mercedes", ...}}
    """
    session = MagicMock()
    session.drivers = sorted(driver_map.keys())
    session.get_driver.side_effect = lambda num: driver_map[num]
    return session


def test_get_drivers_info_known_team_colour():
    session = _make_drivers_session({
        "44": {
            "Abbreviation": "HAM",
            "TeamName": "Mercedes",
            "FirstName": "Lewis",
            "LastName": "Hamilton",
        }
    })
    result = f1.get_drivers_info(session)
    assert len(result) == 1
    assert result[0]["abbr"] == "HAM"
    assert result[0]["colour"] == "#00D2BE"  # Mercedes official colour
    assert result[0]["name"] == "Lewis Hamilton"
    assert result[0]["team"] == "Mercedes"


def test_get_drivers_info_teammate_gets_brightened_colour():
    """Second driver sharing a team receives a lightened (+60 RGB) shade."""
    session = _make_drivers_session({
        "44": {"Abbreviation": "HAM", "TeamName": "Mercedes",
               "FirstName": "Lewis", "LastName": "Hamilton"},
        "63": {"Abbreviation": "RUS", "TeamName": "Mercedes",
               "FirstName": "George", "LastName": "Russell"},
    })
    result = f1.get_drivers_info(session)
    colours = [d["colour"] for d in result]
    assert colours[0] != colours[1]

    base = "#00D2BE"
    r0 = int(base[1:3], 16)   # 0
    g0 = int(base[3:5], 16)   # 210
    b0 = int(base[5:7], 16)   # 190

    bright = colours[1]
    r1 = int(bright[1:3], 16)
    g1 = int(bright[3:5], 16)
    b1 = int(bright[5:7], 16)

    assert r1 == min(255, r0 + 60)
    assert g1 == min(255, g0 + 60)
    assert b1 == min(255, b0 + 60)


def test_get_drivers_info_unknown_team_uses_fallback():
    session = _make_drivers_session({
        "99": {
            "Abbreviation": "TST",
            "TeamName": "Unknown Team XYZ",
            "FirstName": "Test",
            "LastName": "Driver",
        }
    })
    result = f1.get_drivers_info(session)
    colour = result[0]["colour"]
    assert colour.startswith("#")
    assert len(colour) == 7


def test_get_drivers_info_fallback_colours_are_distinct():
    """Multiple unknown-team drivers all get distinct fallback colours."""
    driver_map = {
        str(n): {
            "Abbreviation": f"D{n:02d}",
            "TeamName": f"Unknown Team {n}",
            "FirstName": f"Driver",
            "LastName": f"{n}",
        }
        for n in range(1, 6)
    }
    session = _make_drivers_session(driver_map)
    result = f1.get_drivers_info(session)
    colours = [d["colour"] for d in result]
    assert len(set(colours)) == len(colours)


# ---------------------------------------------------------------------------
# OpenF1Data.get_live_session
# ---------------------------------------------------------------------------


async def test_openf1_get_live_session_returns_most_recent():
    client = OpenF1Data()
    mock_sessions = [
        {"session_key": 1, "date_start": "2024-01-01T12:00:00"},
        {"session_key": 3, "date_start": "2024-03-15T12:00:00"},
        {"session_key": 2, "date_start": "2024-02-10T12:00:00"},
    ]
    with patch.object(client, "_get", new=AsyncMock(return_value=mock_sessions)):
        result = await client.get_live_session()
    assert result["session_key"] == 3


async def test_openf1_get_live_session_no_sessions():
    client = OpenF1Data()
    with patch.object(client, "_get", new=AsyncMock(return_value=None)):
        result = await client.get_live_session()
    assert result is None


async def test_openf1_get_live_session_empty_list():
    client = OpenF1Data()
    with patch.object(client, "_get", new=AsyncMock(return_value=[])):
        result = await client.get_live_session()
    assert result is None


# ---------------------------------------------------------------------------
# JolpicaData — data parsing
# ---------------------------------------------------------------------------


async def test_jolpica_get_races_parses_mrdata():
    client = JolpicaData()
    mock_data = {
        "MRData": {
            "RaceTable": {
                "Races": [
                    {
                        "round": "1",
                        "raceName": "Bahrain Grand Prix",
                        "Circuit": {
                            "circuitId": "bahrain",
                            "circuitName": "Bahrain International Circuit",
                            "Location": {"country": "Bahrain"},
                        },
                    }
                ]
            }
        }
    }
    with patch.object(client, "_get", new=AsyncMock(return_value=mock_data)):
        result = await client.get_races(2024)
    assert len(result) == 1
    assert result[0]["raceName"] == "Bahrain Grand Prix"


async def test_jolpica_get_races_returns_empty_on_none():
    client = JolpicaData()
    with patch.object(client, "_get", new=AsyncMock(return_value=None)):
        result = await client.get_races(2024)
    assert result == []


async def test_jolpica_get_races_returns_empty_on_missing_key():
    client = JolpicaData()
    with patch.object(client, "_get", new=AsyncMock(return_value={"MRData": {}})):
        result = await client.get_races(2024)
    assert result == []


async def test_jolpica_get_results_parses_first_race():
    client = JolpicaData()
    mock_data = {
        "MRData": {
            "RaceTable": {
                "Races": [
                    {"Results": [{"position": "1", "Driver": {"driverId": "max_verstappen"}}]}
                ]
            }
        }
    }
    with patch.object(client, "_get", new=AsyncMock(return_value=mock_data)):
        result = await client.get_results(2024, 1)
    assert len(result) == 1
    assert result[0]["position"] == "1"


async def test_jolpica_get_results_returns_empty_on_none():
    client = JolpicaData()
    with patch.object(client, "_get", new=AsyncMock(return_value=None)):
        result = await client.get_results(2024, 1)
    assert result == []


async def test_jolpica_get_standings_after_round_parses_standings():
    client = JolpicaData()
    mock_data = {
        "MRData": {
            "StandingsTable": {
                "StandingsLists": [
                    {
                        "DriverStandings": [
                            {
                                "position": "1",
                                "points": "75",
                                "Driver": {"driverId": "max_verstappen", "code": "VER"},
                            }
                        ]
                    }
                ]
            }
        }
    }
    with patch.object(client, "_get", new=AsyncMock(return_value=mock_data)):
        result = await client.get_standings_after_round(2024, 3)
    assert len(result) == 1
    assert result[0]["Driver"]["code"] == "VER"
    assert result[0]["points"] == "75"


async def test_jolpica_get_standings_after_round_returns_empty_on_none():
    client = JolpicaData()
    with patch.object(client, "_get", new=AsyncMock(return_value=None)):
        result = await client.get_standings_after_round(2024, 1)
    assert result == []


async def test_jolpica_get_standings_progression_sorted_by_round():
    client = JolpicaData()
    races = [
        {"round": "3", "raceName": "Race 3", "date": "2024-05-05"},
        {"round": "1", "raceName": "Race 1", "date": "2024-03-02"},
        {"round": "2", "raceName": "Race 2", "date": "2024-03-23"},
    ]
    standings = [{"position": "1", "points": "25", "Driver": {"code": "VER"}}]

    async def fake_get(path: str) -> dict:
        if "driverStandings" in path:
            return {
                "MRData": {
                    "StandingsTable": {
                        "StandingsLists": [{"DriverStandings": standings}]
                    }
                }
            }
        return {
            "MRData": {
                "RaceTable": {"Races": races}
            }
        }

    with patch.object(client, "_get", new=AsyncMock(side_effect=fake_get)):
        result = await client.get_standings_progression(2024)

    assert [r["round"] for r in result] == [1, 2, 3]


async def test_jolpica_get_constructor_standings_parses_data():
    client = JolpicaData()
    mock_data = {
        "MRData": {
            "StandingsTable": {
                "StandingsLists": [
                    {
                        "ConstructorStandings": [
                            {"position": "1", "points": "150",
                             "Constructor": {"constructorId": "red_bull", "name": "Red Bull"}}
                        ]
                    }
                ]
            }
        }
    }
    with patch.object(client, "_get", new=AsyncMock(return_value=mock_data)):
        result = await client.get_constructor_standings(2024)
    assert len(result) == 1
    assert result[0]["Constructor"]["name"] == "Red Bull"
