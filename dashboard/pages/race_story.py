from typing import Optional
"""
Race Story view: animated lap-by-lap position chart with race events.
"""
import httpx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


@st.cache_data(ttl=300)
def _fetch(year: int, round_num: int, backend_url: str) -> Optional[dict]:
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

    # ---- Driver highlight selector ----
    all_abbrs = sorted(positions.keys())
    highlighted = st.multiselect(
        "Highlight drivers (others greyed out)",
        options=all_abbrs,
        default=[],
        format_func=lambda a: f"{a} — {drivers.get(a, {}).get('name', a)}",
        placeholder="Select drivers to highlight, or leave empty to show all",
    )

    laps = list(range(1, total_laps + 1))

    # ---- Build position chart ----
    fig = go.Figure()

    for driver_abbr, pos_list in sorted(positions.items()):
        driver_info = drivers.get(driver_abbr, {})
        colour = driver_info.get("colour", "#888888")
        name = driver_info.get("name", driver_abbr)
        team = driver_info.get("team", "")

        # Grey out this driver if the user made a selection AND this driver is NOT in it
        is_greyed = bool(highlighted) and (driver_abbr not in highlighted)

        if is_greyed:
            line_colour = "#444444"
            line_width = 1.0
            opacity = 0.3
        else:
            line_colour = colour
            line_width = 2.5 if highlighted else 2.0
            opacity = 1.0

        padded = (pos_list + [None] * total_laps)[:total_laps]

        fig.add_trace(
            go.Scatter(
                x=laps,
                y=padded,
                mode="lines",
                name=driver_abbr,
                line=dict(color=line_colour, width=line_width),
                opacity=opacity,
                hovertemplate=(
                    f"<b>{name}</b><br>"
                    f"Team: {team}<br>"
                    "Lap: %{x}<br>"
                    "Position: %{y}<extra></extra>"
                ),
                connectgaps=False,
                legendrank=1 if is_highlighted else 999,
            )
        )

    # Y-axis inverted: P1 at top
    fig.update_yaxes(
        autorange="reversed",
        tickvals=list(range(1, 21)),
        title="Position",
        gridcolor="#2a2a2a",
    )
    fig.update_xaxes(title="Lap", gridcolor="#2a2a2a")

    # Overlay race events — group SC/VSC pairs to shade the full period
    # Find matching END events to draw filled regions
    sc_start = None
    vsc_start = None
    event_markers = []  # (lap, type, label, colour) for vertical lines / regions

    for event in sorted(events, key=lambda e: e.get("lap", 0)):
        lap = event.get("lap", 0)
        etype = event.get("type", "")
        if etype == "SAFETY_CAR":
            sc_start = lap
        elif etype == "SC_END" and sc_start is not None:
            fig.add_vrect(
                x0=sc_start - 0.3, x1=lap + 0.3,
                fillcolor="#FFFF00", opacity=0.10, line_width=0,
            )
            fig.add_annotation(
                x=sc_start, y=0.5, yref="paper",
                text=f"🟡 SC L{sc_start}–{lap}", showarrow=False,
                font=dict(color="#FFDD00", size=10),
                bgcolor="#111111", bordercolor="#FFDD00", borderwidth=1,
                xanchor="left",
            )
            sc_start = None
        elif etype == "VSC":
            vsc_start = lap
        elif etype == "VSC_END" and vsc_start is not None:
            fig.add_vrect(
                x0=vsc_start - 0.3, x1=lap + 0.3,
                fillcolor="#FFA500", opacity=0.10, line_width=0,
            )
            fig.add_annotation(
                x=vsc_start, y=0.42, yref="paper",
                text=f"🟠 VSC L{vsc_start}–{lap}", showarrow=False,
                font=dict(color="#FFA500", size=10),
                bgcolor="#111111", bordercolor="#FFA500", borderwidth=1,
                xanchor="left",
            )
            vsc_start = None
        elif etype == "RED_FLAG":
            fig.add_vline(
                x=lap, line_dash="dash", line_color="#FF3333", line_width=2,
            )
            fig.add_annotation(
                x=lap, y=0.34, yref="paper",
                text=f"🔴 Red Flag L{lap}", showarrow=False,
                font=dict(color="#FF3333", size=10),
                bgcolor="#111111", bordercolor="#FF3333", borderwidth=1,
                xanchor="left",
            )

    # If SC/VSC never ended (end of race), still shade from start to last lap
    if sc_start is not None:
        fig.add_vrect(x0=sc_start - 0.3, x1=total_laps + 0.3, fillcolor="#FFFF00", opacity=0.10, line_width=0)
    if vsc_start is not None:
        fig.add_vrect(x0=vsc_start - 0.3, x1=total_laps + 0.3, fillcolor="#FFA500", opacity=0.10, line_width=0)

    fig.update_layout(
        height=620,
        plot_bgcolor="#0f0f0f",
        paper_bgcolor="#0f0f0f",
        font_color="#ffffff",
        legend=dict(
            orientation="v", x=1.01, y=1,
            font=dict(size=10),
            tracegroupgap=0,
            # Single-click legend item = isolate that driver (grey others)
            # Double-click = restore all
            itemclick="toggleothers",
            itemdoubleclick="toggle",
        ),
        margin=dict(l=50, r=130, t=20, b=50),
        hovermode="x unified",
    )

    # Re-order traces so highlighted ones are drawn on top of greyed ones
    if highlighted:
        traces = list(fig.data)
        others = [t for t in traces if t.name not in highlighted]
        highlights = [t for t in traces if t.name in highlighted]
        fig.data = tuple(others + highlights)

    st.plotly_chart(fig, use_container_width=True)

    # ---- Race events legend ----
    if events:
        with st.expander(f"Race Events ({len(events)})"):
            icon_map = {
                "SAFETY_CAR": "🟡 Safety Car In",
                "SC_END": "🟡 Safety Car Out",
                "VSC": "🟠 Virtual Safety Car In",
                "VSC_END": "🟠 Virtual Safety Car Out",
                "RED_FLAG": "🔴 Red Flag",
            }
            for e in sorted(events, key=lambda x: x["lap"]):
                icon = icon_map.get(e["type"], "ℹ️")
                st.write(f"**Lap {e['lap']}** — {icon}: *{e['message']}*")

    # ---- Position change table ----
    st.markdown("#### Position Changes (Grid → Finish)")
    changes = []
    for driver_abbr, pos_list in positions.items():
        valid_pos = [p for p in pos_list if p is not None]
        if not valid_pos:
            continue
        start = valid_pos[0]
        end = valid_pos[-1]
        delta = start - end
        changes.append(
            {
                "Driver": driver_abbr,
                "Name": drivers.get(driver_abbr, {}).get("name", driver_abbr),
                "Team": drivers.get(driver_abbr, {}).get("team", ""),
                "Grid": start,
                "Finish": end,
                "Positions Gained": f"+{delta}" if delta > 0 else str(delta),
            }
        )

    if changes:
        df = pd.DataFrame(changes).sort_values("Finish")
        st.dataframe(df, use_container_width=True, hide_index=True)
