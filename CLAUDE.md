# F1 Race Intelligence Dashboard — Claude Code Instructions

## Critical F1 Colour Standards

### Tyre Colours (ALWAYS use these exact hex values)
```python
TYRE_COLOURS = {
    "SOFT": "#FF3333",
    "MEDIUM": "#FFF200",
    "HARD": "#FFFFFF",
    "INTERMEDIATE": "#39B54A",
    "WET": "#0067FF",
}
```

### Team Colours
- Use `fastf1.plotting.get_team_color(team_name, session)` for official team colours
- Fallback: OpenF1 `team_colour` field — prepend `#` (OpenF1 returns hex without `#`)
- NEVER use random colours for drivers or teams

## Visualisation Rules

### Position Charts
- **Y-axis MUST be inverted**: `fig.update_yaxes(autorange="reversed")` — P1 at top, P20 at bottom
- Y-axis ticks: integers 1-20 only
- Forward-fill NaN positions for DNF drivers; set None after last recorded lap (renders as gap)

### Lap Time Charts
- **NEVER show absolute lap times** — always show delta to median lap time
- Formula: `delta = lap_time - session.laps['LapTime'].median()`
- Absolute times are misleading across tyre stints

### Telemetry
- **ALWAYS smooth raw telemetry** with rolling average of 3 samples before displaying
- `df[['Speed', 'Throttle', 'Brake', 'nGear']] = df[['Speed', 'Throttle', 'Brake', 'nGear']].rolling(3).mean()`

## Data Source Rules

### FastF1
- Cache directory: `./f1_cache/` (always relative to project root)
- Enable at import: `fastf1.Cache.enable_cache('./f1_cache/')`
- Use `session.laps.Position` for lap-by-lap position data (already lap-aligned, preferred over OpenF1 /position endpoint)
- `pick_driver()` takes **abbreviations** (e.g., "VER"), NOT integers
- In-memory session cache: store loaded sessions in module-level dict `_session_cache = {}` keyed by `(year, round, type)`

### OpenF1 API
- Base URL: `https://api.openf1.org/v1`
- No authentication required
- Rate limit: cache live responses every 5 minutes (TTL_LIVE)
- Endpoints used: /sessions, /drivers, /stints, /pit, /race_control, /position

### Jolpica API
- Base URL: `https://api.jolpi.ca/ergast/f1`
- Always access data via `MRData.RaceTable.Races` or `MRData.StandingsTable.StandingsLists`
- Rate limit: ~4 req/s — use `asyncio.Semaphore(4)` for concurrent calls
- Standings progression: cumulative per round (do NOT subtract to get per-race delta)

## Caching Policy
- `TTL_LIVE = 300` (5 minutes) — live sessions, live position data
- `TTL_HISTORICAL = 86400` (24 hours) — race results, standings, telemetry, strategy
- Cache keys: `"races:2024"`, `"story:2024:5"`, `"telemetry:2024:5:VER"`, `"live:session"`
- SQLite DB path: `./data/cache/f1_cache.db` (Docker volume-mounted)

## Architecture Overview

```
backend/          FastAPI service (port 8000)
  main.py         App init, CORS, startup event
  cache.py        SQLite TTL cache (aiosqlite)
  f1_data.py      Data access: FastF1Data, OpenF1Data, JolpicaData
  routers/
    races.py      GET /races/{year}, GET /race/{year}/{round}/story
    strategy.py   GET /race/{year}/{round}/strategy + undercut detector
    telemetry.py  GET /race/{year}/{round}/telemetry/{driver}
    standings.py  GET /season/{year}/standings
    live.py       GET /live/session

dashboard/        Streamlit service (port 8501)
  app.py          Entry point, sidebar, navigation
  pages/
    race_story.py
    strategy_board.py
    driver_telemetry.py
    season_standings.py
    live_race.py

data/cache/       SQLite + FastF1 cache (gitignored, Docker bind mount)
f1_cache/         FastF1 disk cache (gitignored, Docker bind mount)
```

## Undercut Detector Algorithm
For each pit stop by driver A on lap L:
1. Find drivers B within 3 positions of A before the stop
2. Compare A's laps L+1..L+3 vs B's laps L..L+2
3. Labels:
   - "Undercut Success": A emerged ahead AND was faster in those laps
   - "Undercut Failed": A pitted but B remained ahead
   - "Overcut Success": B pitted first; A stayed out and came out ahead
   - "Neutral": no meaningful position change

## Do NOT
- Do NOT use F1's official API (not free)
- Do NOT store large telemetry DataFrames in SQLite — cache FastF1 sessions to disk
- Do NOT hardcode driver numbers
- Do NOT show absolute lap times on charts
- Do NOT skip telemetry smoothing
- Do NOT use `localhost` in Streamlit when running in Docker — use `BACKEND_URL` env var
