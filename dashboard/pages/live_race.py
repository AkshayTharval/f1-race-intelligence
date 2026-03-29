"""
Live Race Mode: current session timing, auto-refreshes every 30s when live.
"""
import httpx
import pandas as pd
import streamlit as st

TYRE_COLOURS = {
    "SOFT": "#FF3333",
    "MEDIUM": "#FFF200",
    "HARD": "#FFFFFF",
    "INTERMEDIATE": "#39B54A",
    "WET": "#0067FF",
    "UNKNOWN": "#888888",
}


def _fetch(backend_url: str) -> dict | None:
    try:
        resp = httpx.get(f"{backend_url}/live/session", timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to load live session: {e}")
        return None


def render(backend_url: str):
    st.markdown("### Live Race Mode")

    # Auto-refresh toggle
    auto_refresh = st.checkbox("Auto-refresh (30s)", value=False, key="live_autorefresh")
    if auto_refresh:
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=30_000, key="live_refresh_counter")
        except ImportError:
            st.warning("streamlit-autorefresh not installed. Manual refresh only.")

    with st.spinner("Fetching live session data..."):
        data = _fetch(backend_url)

    if not data:
        st.warning("Could not fetch live session data.")
        return

    is_live = data.get("is_live", False)
    session_name = data.get("session_name", "Race")
    circuit = data.get("circuit", "")
    location = data.get("location", "")
    country = data.get("country", "")
    year = data.get("year", "")
    date_start = data.get("date_start", "")

    # Status badge
    if is_live:
        st.markdown(
            '<span style="background:#e10600;color:white;padding:4px 12px;border-radius:4px;font-weight:bold;">🔴 LIVE</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span style="background:#444;color:white;padding:4px 12px;border-radius:4px;">⏸ MOST RECENT SESSION</span>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f"**{year} {session_name}** — {location}, {country} | {date_start[:10] if date_start else 'N/A'}"
    )
    st.markdown("---")

    drivers = data.get("drivers", [])
    if not drivers:
        st.info("No driver data available for this session.")
        return

    # Build timing table
    rows = []
    for d in drivers:
        compound = d.get("compound", "UNKNOWN").upper()
        tyre_colour = TYRE_COLOURS.get(compound, "#888888")
        rows.append(
            {
                "Pos": d.get("position", "?"),
                "Driver": d.get("abbr", "?"),
                "Name": d.get("name", ""),
                "Team": d.get("team", ""),
                "Compound": compound,
                "Tyre Age": d.get("tyre_age", 0),
                "Colour": tyre_colour,
                "Team Colour": d.get("colour", "#888888"),
            }
        )

    df = pd.DataFrame(rows)

    # Display with team colours
    def colour_row(row):
        tc = row.get("Team Colour", "#888888")
        return [f"color: {tc}"] + [""] * (len(row) - 1)

    display_df = df[["Pos", "Driver", "Name", "Team", "Compound", "Tyre Age"]].copy()

    # Compound column with tyre colour emoji
    def fmt_compound(row):
        c = row["Compound"]
        colour = TYRE_COLOURS.get(c, "#888888")
        return f'<span style="color:{colour};font-weight:bold;">{c}</span>'

    # Use st.dataframe with a styled view
    st.dataframe(
        display_df.style.apply(
            lambda x: [f"color: {df.loc[x.name, 'Team Colour']}" if col == "Driver" else "" for col in display_df.columns],
            axis=1,
        ),
        use_container_width=True,
        hide_index=True,
    )

    # Tyre compound legend
    st.markdown("#### Tyre Legend")
    leg_cols = st.columns(5)
    for i, (compound, colour) in enumerate(
        [("SOFT", "#FF3333"), ("MEDIUM", "#FFF200"), ("HARD", "#FFFFFF"), ("INTERMEDIATE", "#39B54A"), ("WET", "#0067FF")]
    ):
        leg_cols[i].markdown(
            f'<div style="background:{colour};color:#000;text-align:center;border-radius:4px;padding:4px;font-weight:bold;">{compound}</div>',
            unsafe_allow_html=True,
        )

    if is_live:
        st.info("🔄 Data refreshes every 30 seconds during live sessions. Toggle auto-refresh above.")
    else:
        st.info("No live session currently active. Showing most recent completed session.")
