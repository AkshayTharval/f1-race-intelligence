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
- **Do NOT use `fastf1.plotting`** — it requires matplotlib which crashes on this environment due to a numpy 1.x/2.x ABI conflict
- Use the hardcoded `TEAM_COLOURS` dict in `backend/f1_data.py::get_drivers_info()`
- Teammates get a brightened variant of their team colour (RGB channels +60, capped at 255) to stay visually distinct
- NEVER use random colours for drivers or teams

## Visualisation Rules

### Position Charts
- **Y-axis MUST be inverted**: `fig.update_yaxes(autorange="reversed")` — P1 at top, P20 at bottom
- Y-axis ticks: integers 1-20 only
- Forward-fill NaN positions for DNF drivers; set `None` after last recorded lap (Plotly renders as a line gap)
- Legend: set `itemclick="toggleothers"` so single-click isolates a driver, double-click restores all

### Lap Time Charts
- **NEVER show absolute lap times** — always show delta to median lap time
- Absolute times are misleading across tyre stints with different compounds

### Telemetry
- **ALWAYS smooth raw telemetry** before displaying: `rolling(3, min_periods=1).mean()`
- Applies to: Speed, Throttle, Brake, nGear

## Data Source Rules

### FastF1
- Cache directory: `./f1_cache/` — enable at import: `fastf1.Cache.enable_cache('./f1_cache/')`
- Use `session.laps.Position` for lap-by-lap positions (lap-aligned, preferred over OpenF1 `/position`)
- `pick_driver()` takes **3-letter abbreviations** ("VER", "HAM"), NOT driver numbers
- `session.drivers` returns **driver numbers** (e.g. `["44", "33"]`), NOT abbreviations
  - Use `session.get_driver(num)["Abbreviation"]` to get the abbreviation
- `session.race_control_messages` has a `Lap` column — use it directly, do NOT attempt time-based lap mapping
  - `Time` column in race control messages is an **absolute datetime**, not a timedelta
- In-memory session cache: `_session_cache = {}` keyed by `(year, round, session_type)`

### OpenF1 API
- Base URL: `https://api.openf1.org/v1`
- No authentication required
- Endpoints used: `/sessions`, `/drivers`, `/stints`, `/pit`, `/race_control`, `/position`
- Cache live responses every 5 minutes (TTL_LIVE = 300)

### Jolpica API
- Base URL: `https://api.jolpi.ca/ergast/f1`
- **All requests require `.json` suffix**: e.g. `/2024.json` not `/2024`
- Access data via `MRData.RaceTable.Races` or `MRData.StandingsTable.StandingsLists`
- Rate limit: ~4 req/s — use `asyncio.Semaphore(4)` for concurrent round fetches
- Standings are cumulative per round — do NOT subtract to get per-race deltas

## Caching Policy
- `TTL_LIVE = 300` (5 minutes) — live sessions
- `TTL_HISTORICAL = 86400` (24 hours) — race results, telemetry, standings
- Cache keys: `"races:2024"`, `"story:2024:5"`, `"telemetry:2024:5:VER"`, `"live:session"`
- SQLite DB path: `./data/cache/f1_cache.db` (Docker volume-mounted)
- Clear cache (`rm -f data/cache/f1_cache.db`) after any data-layer changes to force fresh fetch

## Python Version Compatibility
- Runtime: Python 3.9 (Anaconda) — do NOT use Python 3.10+ syntax
- Use `Optional[dict]` not `dict | None` (union syntax requires 3.10+)
- Use `Optional[list]` not `list[dict]` for return type hints
- Use plain `dict` / `list` for variable annotations, not `dict[str, int]`
- Import: `from typing import Optional` at top of each file

## Known Environment Issues
- `numexpr` and `bottleneck` (Anaconda) crash on numpy 2.x — uninstall both: `pip uninstall numexpr bottleneck`
- `fastf1.plotting` and `matplotlib` crash on numpy 2.x — do not import either
- Streamlit MPA: placing `.py` files in `dashboard/pages/` triggers Streamlit's built-in navigation; use relative imports (`from pages.foo import render`) not `from dashboard.pages.foo import render`

## Architecture Overview

```
backend/          FastAPI service (port 8000)
  main.py         App init, CORS, startup pre-warm task
  cache.py        SQLite TTL cache (aiosqlite), asyncio.Lock for write safety
  f1_data.py      FastF1Data, OpenF1Data, JolpicaData singletons
  routers/
    races.py      GET /races/{year}  +  GET /race/{year}/{round}/story
    strategy.py   GET /race/{year}/{round}/strategy  (undercut detector)
    telemetry.py  GET /race/{year}/{round}/telemetry/{driver}
    standings.py  GET /season/{year}/standings
    live.py       GET /live/session

dashboard/        Streamlit service (port 8501)
  app.py          Entry point — sidebar year/race/view selectors, BACKEND_URL env var
  pages/          Imported as modules by app.py, each exports render()
    race_story.py
    strategy_board.py
    driver_telemetry.py
    season_standings.py
    live_race.py

data/cache/       SQLite DB (gitignored, Docker bind mount)
f1_cache/         FastF1 disk cache (gitignored, Docker bind mount)
screenshots/      PNG screenshots for README
```

## Undercut Detector Algorithm
For each pit stop by driver A on lap L:
1. Find drivers B within 3 positions of A before the stop
2. Compare A's laps L+1..L+3 vs B's laps L..L+2 in seconds
3. Labels:
   - "Undercut Success": A emerged ahead AND was faster in those laps
   - "Undercut Failed": A pitted but B remained ahead
   - "Overcut Success": B pitted first; A stayed out and came out ahead
   - "Neutral": no meaningful position change

## Do NOT
- Do NOT use F1's official API (not free/accessible)
- Do NOT use `fastf1.plotting` or `matplotlib` (crashes due to numpy ABI conflict)
- Do NOT store large telemetry DataFrames in SQLite — cache FastF1 sessions to disk only
- Do NOT hardcode driver numbers — always derive from session data
- Do NOT show absolute lap times on charts — use delta to median
- Do NOT skip telemetry smoothing — always apply rolling(3) before returning
- Do NOT use `localhost` for BACKEND_URL in Streamlit when running in Docker — use the `BACKEND_URL` env var
- Do NOT use Python 3.10+ type hint syntax (`X | None`, `list[dict]`) — use `Optional[X]`
- Do NOT attempt to map race control message timestamps to laps using time arithmetic — use `row["Lap"]` directly
