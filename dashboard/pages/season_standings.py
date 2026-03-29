from typing import Optional
"""
Season Standings: championship points progression and teammate head-to-head.
"""
import httpx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


@st.cache_data(ttl=300)
def _fetch(year: int, backend_url: str) -> Optional[dict]:
    try:
        resp = httpx.get(f"{backend_url}/season/{year}/standings", timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to load standings: {e}")
        return None


def render(year: int, backend_url: str):
    st.markdown(f"### {year} Season Standings")

    with st.spinner("Loading season standings..."):
        data = _fetch(year, backend_url)

    if not data:
        st.warning("No standings data available.")
        return

    rounds = data.get("rounds", [])
    all_drivers = data.get("drivers", [])
    constructor_standings = data.get("constructor_standings", [])

    if not rounds:
        st.warning("No round data found.")
        return

    tab1, tab2, tab3 = st.tabs(["Driver Championship", "Constructors", "Teammate H2H"])

    # ---- Driver Championship Progression ----
    with tab1:
        st.markdown("#### Championship Points Progression")

        # Build long-form DataFrame
        rows = []
        for rnd in rounds:
            for driver_code, pts in rnd["points"].items():
                rows.append(
                    {
                        "Round": rnd["round"],
                        "Race": rnd["race_name"],
                        "Driver": driver_code,
                        "Points": pts,
                    }
                )
        if not rows:
            st.warning("No points data found.")
            return

        df = pd.DataFrame(rows)

        # Get final standings to order legend
        final_round = df["Round"].max()
        final_pts = (
            df[df["Round"] == final_round]
            .sort_values("Points", ascending=False)["Driver"]
            .tolist()
        )

        fig = px.line(
            df,
            x="Round",
            y="Points",
            color="Driver",
            category_orders={"Driver": final_pts},
            markers=True,
            hover_data={"Race": True},
            labels={"Round": "Round", "Points": "Championship Points"},
        )
        # Race names on x-axis
        race_names = {rnd["round"]: rnd["race_name"].replace(" Grand Prix", "") for rnd in rounds}
        fig.update_xaxes(
            tickvals=list(race_names.keys()),
            ticktext=list(race_names.values()),
            tickangle=-45,
            gridcolor="#333333",
        )
        fig.update_yaxes(gridcolor="#333333")
        fig.update_layout(
            height=550,
            plot_bgcolor="#0f0f0f",
            paper_bgcolor="#0f0f0f",
            font_color="#ffffff",
            legend=dict(title="Driver", orientation="v", x=1.01),
            margin=dict(l=60, r=120, t=30, b=120),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Final standings table
        if final_pts:
            final_df = (
                df[df["Round"] == final_round]
                .sort_values("Points", ascending=False)
                .reset_index(drop=True)
            )
            final_df.index = final_df.index + 1
            final_df.index.name = "Pos"
            st.dataframe(final_df[["Driver", "Points"]], use_container_width=True)

    # ---- Constructor Standings ----
    with tab2:
        st.markdown("#### Constructor Standings")
        if constructor_standings:
            con_rows = []
            for entry in constructor_standings:
                con_rows.append(
                    {
                        "Pos": int(entry.get("position", 0)),
                        "Constructor": entry.get("Constructor", {}).get("name", ""),
                        "Nationality": entry.get("Constructor", {}).get("nationality", ""),
                        "Points": float(entry.get("points", 0)),
                        "Wins": int(entry.get("wins", 0)),
                    }
                )
            con_df = pd.DataFrame(con_rows).sort_values("Pos")
            st.dataframe(con_df, use_container_width=True, hide_index=True)

            fig_con = px.bar(
                con_df,
                x="Constructor",
                y="Points",
                color="Constructor",
                labels={"Points": "Championship Points"},
                text="Points",
            )
            fig_con.update_layout(
                plot_bgcolor="#0f0f0f",
                paper_bgcolor="#0f0f0f",
                font_color="#ffffff",
                showlegend=False,
                margin=dict(l=60, r=30, t=30, b=80),
            )
            st.plotly_chart(fig_con, use_container_width=True)
        else:
            st.info("Constructor standings not available for this season.")

    # ---- Teammate Head-to-Head ----
    with tab3:
        st.markdown("#### Teammate Head-to-Head")

        # Build team → drivers mapping from all_drivers
        teams: dict[str, list[str]] = {}
        for d in all_drivers:
            team = d.get("constructor", "Unknown")
            code = d.get("code", "???")
            teams.setdefault(team, []).append(code)

        team_options = [t for t, ds in teams.items() if len(ds) >= 2]
        if not team_options:
            st.info("Teammate comparison requires at least one team with 2+ drivers.")
            return

        selected_team = st.selectbox("Select Team", team_options)
        teammates = teams[selected_team][:2]
        d1, d2 = teammates[0], teammates[1]

        # Build comparison: for each round who scored more
        d1_wins = 0
        d2_wins = 0
        h2h_rows = []
        for rnd in rounds:
            pts = rnd["points"]
            p1 = pts.get(d1, 0)
            p2 = pts.get(d2, 0)
            winner = d1 if p1 > p2 else (d2 if p2 > p1 else "Tie")
            if p1 > p2:
                d1_wins += 1
            elif p2 > p1:
                d2_wins += 1
            h2h_rows.append(
                {
                    "Round": rnd["round"],
                    "Race": rnd["race_name"].replace(" Grand Prix", ""),
                    d1: p1,
                    d2: p2,
                    "Better": winner,
                }
            )

        col1, col2, col3 = st.columns(3)
        col1.metric(d1, f"{d1_wins} rounds ahead")
        col2.metric("vs", "")
        col3.metric(d2, f"{d2_wins} rounds ahead")

        h2h_df = pd.DataFrame(h2h_rows)
        st.dataframe(h2h_df, use_container_width=True, hide_index=True)
