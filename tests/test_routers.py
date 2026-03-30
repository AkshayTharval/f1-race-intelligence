"""
Unit tests for FastAPI routers.

Uses TestClient with mocked cache and data-layer dependencies so no real
network calls or FastF1 disk access is needed.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.routers.live import _is_session_live


# ---------------------------------------------------------------------------
# _is_session_live (pure function — no fixtures needed)
# ---------------------------------------------------------------------------


def test_is_session_live_future_date():
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    assert _is_session_live({"date_end": future}) is True


def test_is_session_live_past_date():
    past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    assert _is_session_live({"date_end": past}) is False


def test_is_session_live_none_date_end():
    """Missing date_end → treat session as live."""
    assert _is_session_live({"date_end": None}) is True


def test_is_session_live_missing_key():
    assert _is_session_live({}) is True


def test_is_session_live_invalid_date_string():
    assert _is_session_live({"date_end": "not-a-date"}) is False


def test_is_session_live_z_suffix_handled():
    """ISO 8601 'Z' suffix is normalised to +00:00."""
    past_z = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert _is_session_live({"date_end": past_z}) is False


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


def test_root_health_check(app_client):
    resp = app_client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "F1 Race Intelligence API"
    assert "/docs" in body["docs"]


def test_root_lists_all_endpoints(app_client):
    resp = app_client.get("/")
    endpoints = resp.json()["endpoints"]
    expected = [
        "GET /races/{year}",
        "GET /race/{year}/{round}/story",
        "GET /race/{year}/{round}/strategy",
        "GET /race/{year}/{round}/telemetry/{driver}",
        "GET /season/{year}/standings",
        "GET /live/session",
    ]
    for ep in expected:
        assert ep in endpoints


# ---------------------------------------------------------------------------
# GET /races/{year}
# ---------------------------------------------------------------------------


_MOCK_RACES = [
    {
        "round": "1",
        "raceName": "Bahrain Grand Prix",
        "Circuit": {
            "circuitName": "Bahrain International Circuit",
            "circuitId": "bahrain",
            "Location": {"country": "Bahrain"},
        },
        "date": "2024-03-02",
    }
]

_MOCK_SESSIONS = [{"session_key": 9001, "round_number": 1}]


def test_get_races_cache_miss_returns_list(app_client):
    with patch("backend.routers.races.get", new_callable=AsyncMock, return_value=None), \
         patch("backend.routers.races.set", new_callable=AsyncMock), \
         patch("backend.routers.races.jolpica_data.get_races",
               new_callable=AsyncMock, return_value=_MOCK_RACES), \
         patch("backend.routers.races.openf1_data.get_sessions",
               new_callable=AsyncMock, return_value=_MOCK_SESSIONS):
        resp = app_client.get("/races/2024")

    assert resp.status_code == 200
    assert resp.headers.get("X-Cache") == "MISS"
    data = resp.json()
    assert len(data) == 1
    assert data[0]["round"] == 1
    assert data[0]["name"] == "Bahrain Grand Prix"
    assert data[0]["session_key"] == 9001


def test_get_races_cache_hit_returns_cached(app_client):
    cached = [{"round": 1, "name": "Bahrain Grand Prix", "session_key": 9001}]
    with patch("backend.routers.races.get", new_callable=AsyncMock, return_value=cached):
        resp = app_client.get("/races/2024")

    assert resp.status_code == 200
    assert resp.headers.get("X-Cache") == "HIT"
    assert resp.json() == cached


def test_get_races_session_key_none_when_unmatched(app_client):
    """If no OpenF1 session matches a round, session_key should be None."""
    with patch("backend.routers.races.get", new_callable=AsyncMock, return_value=None), \
         patch("backend.routers.races.set", new_callable=AsyncMock), \
         patch("backend.routers.races.jolpica_data.get_races",
               new_callable=AsyncMock, return_value=_MOCK_RACES), \
         patch("backend.routers.races.openf1_data.get_sessions",
               new_callable=AsyncMock, return_value=[]):
        resp = app_client.get("/races/2024")

    assert resp.status_code == 200
    assert resp.json()[0]["session_key"] is None


# ---------------------------------------------------------------------------
# GET /race/{year}/{round}/story
# ---------------------------------------------------------------------------


def test_get_race_story_cache_miss_returns_data(app_client):
    mock_session = MagicMock()
    mock_positions = {"VER": [1, 1, 2], "HAM": [2, 2, 1]}
    mock_events = [{"lap": 10, "type": "VSC", "message": "VSC DEPLOYED"}]
    mock_drivers = [{"abbr": "VER", "name": "Max Verstappen", "team": "Red Bull Racing",
                     "colour": "#3671C6"}]

    with patch("backend.routers.races.get", new_callable=AsyncMock, return_value=None), \
         patch("backend.routers.races.set", new_callable=AsyncMock), \
         patch("backend.routers.races.fastf1_data.get_session", return_value=mock_session), \
         patch("backend.routers.races.fastf1_data.get_lap_positions",
               return_value=mock_positions), \
         patch("backend.routers.races.fastf1_data.get_race_events",
               return_value=mock_events), \
         patch("backend.routers.races.fastf1_data.get_drivers_info",
               return_value=mock_drivers):
        resp = app_client.get("/race/2024/1/story")

    assert resp.status_code == 200
    body = resp.json()
    assert body["year"] == 2024
    assert body["round"] == 1
    assert body["total_laps"] == 3
    assert "VER" in body["positions"]
    assert body["events"][0]["type"] == "VSC"


def test_get_race_story_session_not_found_returns_404(app_client):
    with patch("backend.routers.races.get", new_callable=AsyncMock, return_value=None), \
         patch("backend.routers.races.fastf1_data.get_session",
               side_effect=Exception("session not found")):
        resp = app_client.get("/race/2024/99/story")

    assert resp.status_code == 404


def test_get_race_story_cache_hit(app_client):
    cached = {"year": 2024, "round": 1, "total_laps": 50, "drivers": [], "positions": {},
              "events": []}
    with patch("backend.routers.races.get", new_callable=AsyncMock, return_value=cached):
        resp = app_client.get("/race/2024/1/story")

    assert resp.status_code == 200
    assert resp.headers.get("X-Cache") == "HIT"
    assert resp.json() == cached


# ---------------------------------------------------------------------------
# GET /race/{year}/{round}/telemetry/{driver}
# ---------------------------------------------------------------------------


_MOCK_TELEMETRY = {
    "driver": "VER",
    "lap_number": 42,
    "lap_time": "1:32.456",
    "telemetry": {
        "distance": [0.0, 10.0, 20.0],
        "speed": [200.0, 220.0, 240.0],
        "throttle": [100.0, 100.0, 80.0],
        "brake": [0.0, 0.0, 20.0],
        "gear": [4.0, 5.0, 5.0],
    },
}


def test_get_telemetry_driver_abbreviation_uppercased(app_client):
    """Lowercase driver in URL must be normalised to uppercase before lookup."""
    with patch("backend.routers.telemetry.get", new_callable=AsyncMock, return_value=None), \
         patch("backend.routers.telemetry.set", new_callable=AsyncMock), \
         patch("backend.routers.telemetry.fastf1_data.get_session",
               return_value=MagicMock()), \
         patch("backend.routers.telemetry.fastf1_data.get_fastest_lap_telemetry",
               return_value=_MOCK_TELEMETRY):
        resp = app_client.get("/race/2024/1/telemetry/ver")  # lowercase

    assert resp.status_code == 200
    assert resp.json()["driver"] == "VER"


def test_get_telemetry_cache_miss_returns_data(app_client):
    with patch("backend.routers.telemetry.get", new_callable=AsyncMock, return_value=None), \
         patch("backend.routers.telemetry.set", new_callable=AsyncMock), \
         patch("backend.routers.telemetry.fastf1_data.get_session",
               return_value=MagicMock()), \
         patch("backend.routers.telemetry.fastf1_data.get_fastest_lap_telemetry",
               return_value=_MOCK_TELEMETRY):
        resp = app_client.get("/race/2024/1/telemetry/VER")

    assert resp.status_code == 200
    assert resp.headers.get("X-Cache") == "MISS"
    body = resp.json()
    assert body["lap_number"] == 42
    assert body["lap_time"] == "1:32.456"
    assert len(body["telemetry"]["speed"]) == 3


def test_get_telemetry_no_telemetry_returns_404(app_client):
    with patch("backend.routers.telemetry.get", new_callable=AsyncMock, return_value=None), \
         patch("backend.routers.telemetry.fastf1_data.get_session",
               return_value=MagicMock()), \
         patch("backend.routers.telemetry.fastf1_data.get_fastest_lap_telemetry",
               return_value=None):
        resp = app_client.get("/race/2024/1/telemetry/XXX")

    assert resp.status_code == 404


def test_get_telemetry_session_not_found_returns_404(app_client):
    with patch("backend.routers.telemetry.get", new_callable=AsyncMock, return_value=None), \
         patch("backend.routers.telemetry.fastf1_data.get_session",
               side_effect=Exception("not found")):
        resp = app_client.get("/race/2024/99/telemetry/VER")

    assert resp.status_code == 404


def test_get_telemetry_cache_hit(app_client):
    with patch("backend.routers.telemetry.get",
               new_callable=AsyncMock, return_value=_MOCK_TELEMETRY):
        resp = app_client.get("/race/2024/1/telemetry/VER")

    assert resp.status_code == 200
    assert resp.headers.get("X-Cache") == "HIT"


# ---------------------------------------------------------------------------
# GET /season/{year}/standings
# ---------------------------------------------------------------------------


_MOCK_PROGRESSION = [
    {
        "round": 1,
        "race_name": "Bahrain Grand Prix",
        "date": "2024-03-02",
        "standings": [
            {
                "points": "25",
                "Driver": {"code": "VER", "driverId": "max_verstappen",
                           "givenName": "Max", "familyName": "Verstappen",
                           "nationality": "Dutch"},
                "Constructors": [{"name": "Red Bull Racing"}],
            }
        ],
    }
]

_MOCK_CONSTRUCTOR_STANDINGS = [
    {"position": "1", "points": "25",
     "Constructor": {"constructorId": "red_bull", "name": "Red Bull Racing"}}
]


def test_get_season_standings_cache_miss_returns_data(app_client):
    with patch("backend.routers.standings.get", new_callable=AsyncMock, return_value=None), \
         patch("backend.routers.standings.set", new_callable=AsyncMock), \
         patch("backend.routers.standings.jolpica_data.get_standings_progression",
               new_callable=AsyncMock, return_value=_MOCK_PROGRESSION), \
         patch("backend.routers.standings.jolpica_data.get_constructor_standings",
               new_callable=AsyncMock, return_value=_MOCK_CONSTRUCTOR_STANDINGS):
        resp = app_client.get("/season/2024/standings")

    assert resp.status_code == 200
    body = resp.json()
    assert body["year"] == 2024
    assert len(body["rounds"]) == 1
    assert body["rounds"][0]["round"] == 1
    assert body["rounds"][0]["points"]["VER"] == 25.0
    assert any(d["code"] == "VER" for d in body["drivers"])
    assert len(body["constructor_standings"]) == 1


def test_get_season_standings_cache_hit(app_client):
    cached = {"year": 2024, "rounds": [], "drivers": [], "constructor_standings": []}
    with patch("backend.routers.standings.get", new_callable=AsyncMock, return_value=cached):
        resp = app_client.get("/season/2024/standings")

    assert resp.status_code == 200
    assert resp.headers.get("X-Cache") == "HIT"


def test_get_season_standings_driver_info_populated(app_client):
    with patch("backend.routers.standings.get", new_callable=AsyncMock, return_value=None), \
         patch("backend.routers.standings.set", new_callable=AsyncMock), \
         patch("backend.routers.standings.jolpica_data.get_standings_progression",
               new_callable=AsyncMock, return_value=_MOCK_PROGRESSION), \
         patch("backend.routers.standings.jolpica_data.get_constructor_standings",
               new_callable=AsyncMock, return_value=[]):
        resp = app_client.get("/season/2024/standings")

    drivers = resp.json()["drivers"]
    ver = next(d for d in drivers if d["code"] == "VER")
    assert ver["name"] == "Max Verstappen"
    assert ver["nationality"] == "Dutch"
    assert ver["constructor"] == "Red Bull Racing"


# ---------------------------------------------------------------------------
# GET /live/session
# ---------------------------------------------------------------------------


_MOCK_LIVE_SESSION = {
    "session_key": 7777,
    "session_name": "Race",
    "circuit_short_name": "Bahrain",
    "location": "Sakhir",
    "country_name": "Bahrain",
    "year": 2024,
    "date_start": "2024-03-02T15:00:00",
    "date_end": None,  # None → is_live=True
}

_MOCK_DRIVERS_RAW = [
    {
        "driver_number": 1,
        "name_acronym": "VER",
        "full_name": "Max Verstappen",
        "team_name": "Red Bull Racing",
        "team_colour": "3671C6",
        "headshot_url": "",
    }
]

_MOCK_POSITIONS_RAW = [{"driver_number": 1, "position": 1}]

_MOCK_STINTS_RAW = [
    {"driver_number": 1, "stint_number": 1, "compound": "MEDIUM", "tyre_age_at_start": 0}
]


def test_get_live_session_cache_miss_returns_data(app_client):
    with patch("backend.routers.live.get", new_callable=AsyncMock, return_value=None), \
         patch("backend.routers.live.set", new_callable=AsyncMock), \
         patch("backend.routers.live.openf1_data.get_live_session",
               new_callable=AsyncMock, return_value=_MOCK_LIVE_SESSION), \
         patch("backend.routers.live.openf1_data.get_drivers",
               new_callable=AsyncMock, return_value=_MOCK_DRIVERS_RAW), \
         patch("backend.routers.live.openf1_data.get_position",
               new_callable=AsyncMock, return_value=_MOCK_POSITIONS_RAW), \
         patch("backend.routers.live.openf1_data.get_stints",
               new_callable=AsyncMock, return_value=_MOCK_STINTS_RAW):
        resp = app_client.get("/live/session")

    assert resp.status_code == 200
    body = resp.json()
    assert body["session_key"] == 7777
    assert body["is_live"] is True
    assert body["circuit"] == "Bahrain"
    assert len(body["drivers"]) == 1
    assert body["drivers"][0]["abbr"] == "VER"
    assert body["drivers"][0]["compound"] == "MEDIUM"
    assert body["drivers"][0]["colour"] == "#3671C6"  # # prefix added


def test_get_live_session_no_session_found(app_client):
    with patch("backend.routers.live.get", new_callable=AsyncMock, return_value=None), \
         patch("backend.routers.live.set", new_callable=AsyncMock), \
         patch("backend.routers.live.openf1_data.get_live_session",
               new_callable=AsyncMock, return_value=None):
        resp = app_client.get("/live/session")

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_live"] is False
    assert body["session_key"] is None
    assert "error" in body


def test_get_live_session_cache_hit(app_client):
    cached = {"is_live": False, "session_key": 7777, "drivers": []}
    with patch("backend.routers.live.get", new_callable=AsyncMock, return_value=cached):
        resp = app_client.get("/live/session")

    assert resp.status_code == 200
    assert resp.headers.get("X-Cache") == "HIT"


def test_get_live_session_drivers_sorted_by_position(app_client):
    drivers_raw = [
        {"driver_number": 33, "name_acronym": "VER", "full_name": "Max Verstappen",
         "team_name": "Red Bull", "team_colour": "3671C6", "headshot_url": ""},
        {"driver_number": 44, "name_acronym": "HAM", "full_name": "Lewis Hamilton",
         "team_name": "Mercedes", "team_colour": "00D2BE", "headshot_url": ""},
    ]
    positions_raw = [
        {"driver_number": 33, "position": 2},
        {"driver_number": 44, "position": 1},
    ]

    with patch("backend.routers.live.get", new_callable=AsyncMock, return_value=None), \
         patch("backend.routers.live.set", new_callable=AsyncMock), \
         patch("backend.routers.live.openf1_data.get_live_session",
               new_callable=AsyncMock, return_value=_MOCK_LIVE_SESSION), \
         patch("backend.routers.live.openf1_data.get_drivers",
               new_callable=AsyncMock, return_value=drivers_raw), \
         patch("backend.routers.live.openf1_data.get_position",
               new_callable=AsyncMock, return_value=positions_raw), \
         patch("backend.routers.live.openf1_data.get_stints",
               new_callable=AsyncMock, return_value=[]):
        resp = app_client.get("/live/session")

    drivers = resp.json()["drivers"]
    positions = [d["position"] for d in drivers]
    assert positions == sorted(positions)  # ascending position order


def test_get_live_session_team_colour_gets_hash_prefix(app_client):
    """Colours without # prefix from OpenF1 must have # prepended."""
    driver_without_hash = [{
        "driver_number": 1,
        "name_acronym": "VER",
        "full_name": "Max Verstappen",
        "team_name": "Red Bull",
        "team_colour": "3671C6",  # no leading #
        "headshot_url": "",
    }]

    with patch("backend.routers.live.get", new_callable=AsyncMock, return_value=None), \
         patch("backend.routers.live.set", new_callable=AsyncMock), \
         patch("backend.routers.live.openf1_data.get_live_session",
               new_callable=AsyncMock, return_value=_MOCK_LIVE_SESSION), \
         patch("backend.routers.live.openf1_data.get_drivers",
               new_callable=AsyncMock, return_value=driver_without_hash), \
         patch("backend.routers.live.openf1_data.get_position",
               new_callable=AsyncMock, return_value=[]), \
         patch("backend.routers.live.openf1_data.get_stints",
               new_callable=AsyncMock, return_value=[]):
        resp = app_client.get("/live/session")

    colour = resp.json()["drivers"][0]["colour"]
    assert colour.startswith("#")
    assert colour == "#3671C6"
