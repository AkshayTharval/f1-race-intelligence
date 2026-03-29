"""
Strategy Board: tyre stint Gantt chart, pit stop timeline, undercut/overcut detector.
"""
import httpx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


@st.cache_data(ttl=300)
def _fetch(year: int, round_num: int, backend_url: str) -> dict | None:
    try:
        resp = httpx.get(f"{backend_url}/race/{year}/{round_num}/strategy", timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to load strategy data: {e}")
        return None


def render(year: int, round_num: int, backend_url: str):
    st.markdown("### Strategy Board — Tyre Strategy & Pit Stop Analysis")

    with st.spinner("Loading strategy data..."):
        data = _fetch(year, round_num, backend_url)

    if not data:
        st.warning("No strategy data available.")
        return

    stints = data.get("stints", [])
    pit_stops = data.get("pit_stops", [])
    drivers_info = data.get("drivers", [])
    tyre_colours = data.get("tyre_colours", {})

    drivers_map = {d["abbr"]: d for d in drivers_info}

    if not stints:
        st.warning("No stint data available for this race.")
        return

    # ---- Tyre strategy Gantt chart ----
    st.markdown("#### Tyre Strategy")

    # Sort drivers by typical finish order (use last stint's lap_end as proxy)
    driver_last_lap = {}
    for s in stints:
        d = s["driver"]
        if d not in driver_last_lap or s["lap_end"] > driver_last_lap[d]:
            driver_last_lap[d] = s["lap_end"]
    sorted_drivers = sorted(driver_last_lap, key=lambda d: driver_last_lap[d], reverse=True)

    fig = go.Figure()
    y_positions = {d: i for i, d in enumerate(sorted_drivers)}

    compound_labels = set()
    for stint in stints:
        driver = stint["driver"]
        compound = stint.get("compound", "UNKNOWN")
        colour = stint.get("colour", "#888888")
        y = y_positions.get(driver, 0)
        lap_start = stint["lap_start"]
        lap_end = stint["lap_end"]
        width = lap_end - lap_start

        label = compound if compound not in compound_labels else None
        compound_labels.add(compound)

        fig.add_trace(
            go.Bar(
                x=[width],
                y=[driver],
                base=[lap_start],
                orientation="h",
                marker=dict(
                    color=colour,
                    line=dict(color="#333333", width=0.5),
                ),
                name=compound if label else "",
                showlegend=label is not None,
                hovertemplate=(
                    f"<b>{driver}</b><br>"
                    f"Compound: {compound}<br>"
                    f"Laps: {lap_start}–{lap_end}<br>"
                    f"Stint: {width} laps<extra></extra>"
                ),
            )
        )

    # Pit stop markers (vertical lines per driver at pit lap)
    for pit in pit_stops:
        driver = pit["driver"]
        lap = pit["lap"]
        y_idx = y_positions.get(driver, 0)
        fig.add_scatter(
            x=[lap],
            y=[driver],
            mode="markers",
            marker=dict(symbol="diamond", size=10, color="white", line=dict(color="black", width=1)),
            showlegend=False,
            hovertemplate=(
                f"<b>Pit Stop — {driver}</b><br>"
                f"Lap: {lap}<br>"
                f"{pit.get('label', '')}: {pit.get('explanation', '')}<extra></extra>"
            ),
        )

    fig.update_layout(
        barmode="overlay",
        xaxis_title="Lap",
        yaxis_title="Driver",
        height=max(400, len(sorted_drivers) * 28),
        plot_bgcolor="#0f0f0f",
        paper_bgcolor="#0f0f0f",
        font_color="#ffffff",
        legend=dict(title="Compound", orientation="h", y=-0.15),
        margin=dict(l=80, r=30, t=30, b=80),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ---- Undercut / Overcut detector ----
    st.markdown("#### Undercut / Overcut Analysis")

    if pit_stops:
        undercut_ok = sum(1 for p in pit_stops if p.get("label") == "Undercut Success")
        undercut_fail = sum(1 for p in pit_stops if p.get("label") == "Undercut Failed")
        overcut_ok = sum(1 for p in pit_stops if p.get("label") == "Overcut Success")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Pit Stops", len(pit_stops))
        col2.metric("Undercut Success", undercut_ok)
        col3.metric("Undercut Failed", undercut_fail)
        col4.metric("Overcut Success", overcut_ok)

        label_colour = {
            "Undercut Success": "🟢",
            "Undercut Failed": "🔴",
            "Overcut Success": "🔵",
            "Neutral": "⚪",
        }
        df_pits = pd.DataFrame(
            [
                {
                    "Driver": p["driver"],
                    "Lap": p["lap"],
                    "Old Compound": p.get("compound_before", ""),
                    "New Compound": p.get("compound_after", ""),
                    "Label": f"{label_colour.get(p.get('label', ''), '⚪')} {p.get('label', 'Neutral')}",
                    "Explanation": p.get("explanation", ""),
                }
                for p in pit_stops
            ]
        )
        st.dataframe(df_pits, use_container_width=True, hide_index=True)
    else:
        st.info("No pit stop data available.")
