"""
Race Story view: animated lap-by-lap position chart with race events.
"""
import httpx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


@st.cache_data(ttl=300)
def _fetch(year: int, round_num: int, backend_url: str) -> dict | None:
    try:
        resp = httpx.get(f"{backend_url}/race/{year}/{round_num}/story", timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to load race story: {e}")
        return None


def render(year: int, round_num: int, backend_url: str):
    st.markdown("### Race Story — Lap-by-Lap Positions")

    with st.spinner("Loading race data... (first load may take 30-60s while FastF1 downloads data)"):
        data = _fetch(year, round_num, backend_url)

    if not data:
        st.warning("No data available. Try a different race.")
        return

    drivers = {d["abbr"]: d for d in data.get("drivers", [])}
    positions = data.get("positions", {})
    events = data.get("events", [])
    total_laps = data.get("total_laps", 0)

    if not positions:
        st.warning("No position data available for this race.")
        return

    # Build position dataframe
    laps = list(range(1, total_laps + 1))
    colour_map = {abbr: d.get("colour", "#888888") for abbr, d in drivers.items()}

    # ---- Main position chart ----
    fig = go.Figure()
    for driver_abbr, pos_list in sorted(positions.items()):
        driver_info = drivers.get(driver_abbr, {})
        colour = colour_map.get(driver_abbr, "#888888")
        name = driver_info.get("name", driver_abbr)
        team = driver_info.get("team", "")

        # Pad/trim to total_laps
        padded = (pos_list + [None] * total_laps)[:total_laps]

        fig.add_trace(
            go.Scatter(
                x=laps,
                y=padded,
                mode="lines",
                name=driver_abbr,
                line=dict(color=colour, width=2),
                hovertemplate=(
                    f"<b>{name}</b><br>"
                    f"Team: {team}<br>"
                    "Lap: %{x}<br>"
                    "Position: %{y}<extra></extra>"
                ),
                connectgaps=False,
            )
        )

    # Y-axis inverted: P1 at top
    fig.update_yaxes(
        autorange="reversed",
        tickvals=list(range(1, 21)),
        title="Position",
        gridcolor="#333333",
    )
    fig.update_xaxes(title="Lap", gridcolor="#333333")

    # Overlay race events
    for event in events:
        lap = event.get("lap", 0)
        etype = event.get("type", "")
        if etype == "SAFETY_CAR":
            fig.add_vrect(
                x0=lap - 0.5,
                x1=lap + 2.5,
                fillcolor="yellow",
                opacity=0.15,
                line_width=0,
                annotation_text="SC",
                annotation_position="top left",
            )
        elif etype == "VSC":
            fig.add_vrect(
                x0=lap - 0.5,
                x1=lap + 1.5,
                fillcolor="orange",
                opacity=0.15,
                line_width=0,
                annotation_text="VSC",
                annotation_position="top left",
            )
        elif etype == "RED_FLAG":
            fig.add_vline(
                x=lap,
                line_dash="dash",
                line_color="red",
                annotation_text="RED FLAG",
                annotation_position="top left",
            )

    fig.update_layout(
        height=600,
        plot_bgcolor="#0f0f0f",
        paper_bgcolor="#0f0f0f",
        font_color="#ffffff",
        legend=dict(
            orientation="v",
            x=1.01,
            y=1,
            font=dict(size=10),
        ),
        margin=dict(l=50, r=120, t=30, b=50),
    )

    st.plotly_chart(fig, use_container_width=True)

    # ---- Race events legend ----
    if events:
        with st.expander("Race Events"):
            for e in events:
                icon = {"SAFETY_CAR": "🟡", "VSC": "🟠", "RED_FLAG": "🔴", "GREEN": "🟢"}.get(
                    e["type"], "ℹ️"
                )
                st.write(f"**Lap {e['lap']}** {icon} {e['message']}")

    # ---- Position change table ----
    st.markdown("#### Position Changes")
    changes = []
    for driver_abbr, pos_list in positions.items():
        valid_pos = [p for p in pos_list if p is not None]
        if not valid_pos:
            continue
        start = valid_pos[0]
        end = valid_pos[-1]
        delta = start - end  # positive = gained positions
        changes.append(
            {
                "Driver": driver_abbr,
                "Name": drivers.get(driver_abbr, {}).get("name", driver_abbr),
                "Team": drivers.get(driver_abbr, {}).get("team", ""),
                "Start": start,
                "Finish": end,
                "Change": f"+{delta}" if delta > 0 else str(delta),
            }
        )

    if changes:
        df = pd.DataFrame(changes).sort_values("Finish")
        st.dataframe(df, use_container_width=True, hide_index=True)
