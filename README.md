# 🏎️ F1 Race Intelligence Dashboard

An interactive Formula 1 data explorer with live telemetry, strategy analysis, and race storytelling — built entirely on **free, open data sources**.

> **Run it in 2 commands:**
> ```bash
> git clone https://github.com/akshaytharval/f1-race-intelligence.git
> cd f1-race-intelligence && docker-compose up
> ```
> Then open **http://localhost:8501**

---

## Features

| View | What it shows |
|------|--------------|
| **Race Story** | Animated lap-by-lap position chart for all 20 drivers with safety car / red flag annotations |
| **Strategy Board** | Tyre stint Gantt chart with official compound colours + undercut/overcut detector |
| **Driver Telemetry** | Fastest lap overlay — speed, throttle, brake, gear comparison for any two drivers |
| **Season Standings** | Championship points progression, constructor standings, teammate head-to-head |
| **Live Race** | Real-time timing (auto-refreshes every 30s during live sessions) |

---

## Screenshots

> *(Add screenshots here once the app is running)*

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     docker-compose                          │
│                                                             │
│  ┌─────────────────────┐    ┌──────────────────────────┐   │
│  │   FastAPI Backend   │    │   Streamlit Dashboard    │   │
│  │   :8000             │◄───│   :8501                  │   │
│  │                     │    │                          │   │
│  │  /races/{year}      │    │  Race Story              │   │
│  │  /race/.../story    │    │  Strategy Board          │   │
│  │  /race/.../strategy │    │  Driver Telemetry        │   │
│  │  /race/.../telemetry│    │  Season Standings        │   │
│  │  /season/.../stand. │    │  Live Race               │   │
│  │  /live/session      │    │                          │   │
│  └──────────┬──────────┘    └──────────────────────────┘   │
│             │                                               │
│  ┌──────────▼──────────────────────────────┐               │
│  │           Data Layer                    │               │
│  │  FastF1 (disk cache ./f1_cache/)        │               │
│  │  OpenF1 API  (live + historical)        │               │
│  │  Jolpica API (historical back to 1950)  │               │
│  │  SQLite TTL cache (./data/cache/)       │               │
│  └─────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Sources

| Source | What it provides | Auth |
|--------|-----------------|------|
| [FastF1](https://docs.fastf1.dev/) | Lap data, telemetry, tyre compounds, session data | None |
| [OpenF1 API](https://openf1.org/) | Live timing, pit stops, race control, driver info | None |
| [Jolpica / Ergast](https://jolpi.ca/) | Historical results & standings back to 1950 | None |

**Cost: $0** — All data sources are completely free.

---

## Quick Start (Local, No Docker)

```bash
# 1. Clone and install
git clone https://github.com/akshaytharval/f1-race-intelligence.git
cd f1-race-intelligence
pip install -r requirements.txt

# 2. Start the API backend
uvicorn backend.main:app --reload
# → API docs at http://localhost:8000/docs

# 3. In another terminal, start the dashboard
streamlit run dashboard/app.py
# → Dashboard at http://localhost:8501
```

---

## API Reference

The FastAPI backend has auto-generated Swagger docs at **http://localhost:8000/docs**

| Endpoint | Description |
|----------|-------------|
| `GET /races/{year}` | List all races in a season |
| `GET /race/{year}/{round}/story` | Lap-by-lap positions + race events |
| `GET /race/{year}/{round}/strategy` | Tyre strategy + undercut/overcut analysis |
| `GET /race/{year}/{round}/telemetry/{driver}` | Smoothed fastest-lap telemetry |
| `GET /season/{year}/standings` | Championship points progression |
| `GET /live/session` | Current or most recent session |

All responses are SQLite-cached:
- **5 minutes** for live session data
- **24 hours** for historical race data

---

## Tech Stack

- **Backend:** Python, FastAPI, FastF1, httpx, aiosqlite
- **Frontend:** Streamlit, Plotly
- **Data:** OpenF1 API, Jolpica (Ergast) API, FastF1 library
- **Infrastructure:** Docker, Docker Compose, SQLite

---

## F1 Colour Standards

This project follows official F1 visual standards:

| Compound | Colour |
|---------|--------|
| Soft | 🔴 `#FF3333` |
| Medium | 🟡 `#FFF200` |
| Hard | ⚪ `#FFFFFF` |
| Intermediate | 🟢 `#39B54A` |
| Wet | 🔵 `#0067FF` |

Team colours sourced from the `fastf1.plotting` module.

---

## Notes

- **First load** of a new race session takes 30–60 seconds while FastF1 downloads timing data. Subsequent loads are instant (disk-cached).
- The `./f1_cache/` directory can grow to **several GB** for a full season of data.
- During 2025 race weekends, the Live Race view auto-refreshes every 30 seconds.

---

## Contributing

PRs welcome! Please follow the visualisation rules in [CLAUDE.md](CLAUDE.md).

---

## License

MIT
