"""
F1 Race Intelligence Dashboard — Streamlit Entry Point
"""
import os

import httpx
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(
    page_title="F1 Race Intelligence",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for F1 branding
st.markdown(
    """
    <style>
    [data-testid="stSidebar"] {
        background-color: #1a1a1a;
    }
    [data-testid="stSidebar"] * {
        color: #ffffff !important;
    }
    .stSelectbox label, .stRadio label {
        color: #ffffff !important;
    }
    h1, h2, h3 {
        color: #e10600;
    }
    .metric-card {
        background: #1a1a1a;
        border-radius: 8px;
        padding: 12px;
        margin: 4px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=300)
def fetch_races(year: int) -> list:
    try:
        resp = httpx.get(f"{BACKEND_URL}/races/{year}", timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to load races for {year}: {e}")
        return []


# ---- Sidebar ----
with st.sidebar:
    st.markdown("## 🏎️ F1 Intelligence")
    st.markdown("---")

    year = st.selectbox(
        "Season",
        options=list(range(2025, 2017, -1)),
        index=0,
    )

    races = fetch_races(year)
    race_options = {f"{r['round']}. {r['name']}": r["round"] for r in races} if races else {}
    race_label = st.selectbox("Race", options=list(race_options.keys()) if race_options else ["Loading..."])
    round_num = race_options.get(race_label, 1)

    st.markdown("---")
    view = st.radio(
        "View",
        options=[
            "Race Story",
            "Strategy Board",
            "Driver Telemetry",
            "Season Standings",
            "Live Race",
        ],
    )
    st.markdown("---")
    st.markdown(
        "<small>Data: FastF1 · OpenF1 · Jolpica</small>",
        unsafe_allow_html=True,
    )

# ---- Main content ----
st.markdown(f"## 🏁 {race_label}" if race_options else "## 🏁 F1 Race Intelligence")

if view == "Race Story":
    from dashboard.pages.race_story import render
    render(year, round_num, BACKEND_URL)

elif view == "Strategy Board":
    from dashboard.pages.strategy_board import render
    render(year, round_num, BACKEND_URL)

elif view == "Driver Telemetry":
    from dashboard.pages.driver_telemetry import render
    render(year, round_num, BACKEND_URL)

elif view == "Season Standings":
    from dashboard.pages.season_standings import render
    render(year, BACKEND_URL)

elif view == "Live Race":
    from dashboard.pages.live_race import render
    render(BACKEND_URL)
