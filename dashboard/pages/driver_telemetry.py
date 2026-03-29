"""
Driver Telemetry: fastest lap overlay — speed, throttle, brake, gear comparison.
"""
import httpx
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots


@st.cache_data(ttl=300)
def _fetch_story(year: int, round_num: int, backend_url: str) -> dict | None:
    try:
        resp = httpx.get(f"{backend_url}/race/{year}/{round_num}/story", timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


@st.cache_data(ttl=300)
def _fetch_telemetry(year: int, round_num: int, driver: str, backend_url: str) -> dict | None:
    try:
        resp = httpx.get(
            f"{backend_url}/race/{year}/{round_num}/telemetry/{driver}", timeout=60
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to load telemetry for {driver}: {e}")
        return None


def render(year: int, round_num: int, backend_url: str):
    st.markdown("### Driver Telemetry — Fastest Lap Comparison")

    story = _fetch_story(year, round_num, backend_url)
    driver_list = (
        sorted([d["abbr"] for d in story.get("drivers", [])]) if story else []
    )
    driver_colours = (
        {d["abbr"]: d.get("colour", "#888888") for d in story.get("drivers", [])}
        if story
        else {}
    )

    if not driver_list:
        st.warning("Could not load driver list. Try another race.")
        return

    col1, col2 = st.columns(2)
    with col1:
        driver1 = st.selectbox("Driver 1", driver_list, index=0)
    with col2:
        default_idx = 1 if len(driver_list) > 1 else 0
        driver2 = st.selectbox("Driver 2", driver_list, index=default_idx)

    with st.spinner("Loading telemetry data..."):
        tele1 = _fetch_telemetry(year, round_num, driver1, backend_url)
        tele2 = _fetch_telemetry(year, round_num, driver2, backend_url) if driver2 != driver1 else None

    if not tele1:
        st.warning(f"No telemetry available for {driver1}.")
        return

    # Lap time metrics
    m_cols = st.columns(2 if tele2 else 1)
    m_cols[0].metric(f"{driver1} Fastest Lap", tele1.get("lap_time", "N/A"), f"Lap {tele1.get('lap_number', '?')}")
    if tele2:
        m_cols[1].metric(f"{driver2} Fastest Lap", tele2.get("lap_time", "N/A"), f"Lap {tele2.get('lap_number', '?')}")

    # Build 4-panel subplot
    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.35, 0.25, 0.2, 0.2],
        subplot_titles=["Speed (km/h)", "Throttle (%)", "Brake", "Gear"],
        vertical_spacing=0.06,
    )

    colour1 = driver_colours.get(driver1, "#FF3333")
    colour2 = driver_colours.get(driver2, "#3399FF") if driver2 else "#3399FF"

    tele1_data = tele1.get("telemetry", {})
    dist1 = tele1_data.get("distance", [])

    def add_driver_traces(tele: dict, colour: str, driver: str, showlegend: bool = True):
        t = tele.get("telemetry", {})
        dist = t.get("distance", [])
        fig.add_trace(
            go.Scatter(
                x=dist, y=t.get("speed", []),
                mode="lines", line=dict(color=colour, width=1.5),
                name=driver, showlegend=showlegend,
                hovertemplate=f"{driver} Speed: %{{y:.0f}} km/h<extra></extra>",
            ),
            row=1, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=dist, y=t.get("throttle", []),
                mode="lines", line=dict(color=colour, width=1.5),
                name=driver, showlegend=False,
                hovertemplate=f"{driver} Throttle: %{{y:.0f}}%<extra></extra>",
            ),
            row=2, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=dist, y=t.get("brake", []),
                mode="lines", line=dict(color=colour, width=1.5),
                fill="tozeroy", fillcolor=colour.replace(")", ", 0.2)").replace("rgb", "rgba") if "rgb" in colour else colour + "33",
                name=driver, showlegend=False,
                hovertemplate=f"{driver} Brake: %{{y:.2f}}<extra></extra>",
            ),
            row=3, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=dist, y=t.get("gear", []),
                mode="lines", line=dict(color=colour, width=1.5, shape="hv"),
                name=driver, showlegend=False,
                hovertemplate=f"{driver} Gear: %{{y:.0f}}<extra></extra>",
            ),
            row=4, col=1,
        )

    add_driver_traces(tele1, colour1, driver1, showlegend=True)
    if tele2:
        add_driver_traces(tele2, colour2, driver2, showlegend=True)

    fig.update_xaxes(title_text="Distance (m)", row=4, col=1, gridcolor="#333333")
    for row in range(1, 5):
        fig.update_xaxes(gridcolor="#333333", row=row, col=1)
        fig.update_yaxes(gridcolor="#333333", row=row, col=1)

    fig.update_layout(
        height=700,
        plot_bgcolor="#0f0f0f",
        paper_bgcolor="#0f0f0f",
        font_color="#ffffff",
        legend=dict(orientation="h", y=1.02, x=0),
        margin=dict(l=60, r=30, t=60, b=50),
    )
    st.plotly_chart(fig, use_container_width=True)
