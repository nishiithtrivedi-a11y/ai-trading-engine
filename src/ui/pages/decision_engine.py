"""
Decision Engine page - top picks by horizon, rejected opportunities.
"""

from __future__ import annotations

import streamlit as st

from src.ui.components.tables import data_table, picks_table
from src.ui.utils.formatters import fmt_timestamp
from src.ui.utils.loaders import (
    load_decision_picks,
    load_decision_rejected,
    load_decision_summary,
)


def render(output_dir: str) -> None:
    st.header("Decision Engine")

    summary, summary_err = load_decision_summary(output_dir)

    if summary:
        st.subheader("Decision Summary")
        s = summary.get("summary", summary)
        cols = st.columns(5)
        with cols[0]:
            st.metric("Total Selected", s.get("total_selected", "N/A"))
        with cols[1]:
            st.metric("Intraday", s.get("intraday_count", "N/A"))
        with cols[2]:
            st.metric("Swing", s.get("swing_count", "N/A"))
        with cols[3]:
            st.metric("Positional", s.get("positional_count", "N/A"))
        with cols[4]:
            st.metric("Rejected", s.get("rejected_count", "N/A"))

        st.caption(f"Generated at: {fmt_timestamp(summary.get('generated_at'))}")
        st.divider()

    # Tabs for each horizon
    tab_intra, tab_swing, tab_pos, tab_rejected = st.tabs([
        "Intraday", "Swing", "Positional", "Rejected"
    ])

    with tab_intra:
        df, err = load_decision_picks("intraday", output_dir)
        if df is not None:
            picks_table(df, title="Top Intraday Picks")
        else:
            st.info(err or "No intraday picks available.")

    with tab_swing:
        df, err = load_decision_picks("swing", output_dir)
        if df is not None:
            picks_table(df, title="Top Swing Picks")
        else:
            st.info(err or "No swing picks available.")

    with tab_pos:
        df, err = load_decision_picks("positional", output_dir)
        if df is not None:
            picks_table(df, title="Top Positional Picks")
        else:
            st.info(err or "No positional picks available.")

    with tab_rejected:
        df, err = load_decision_rejected(output_dir)
        if df is not None:
            st.subheader("Rejected Opportunities")

            # Show rejection reason distribution
            if "rejection_reasons" in df.columns:
                st.caption("Rejection Reason Distribution")
                reasons = df["rejection_reasons"].value_counts()
                st.bar_chart(reasons.head(10))

            data_table(df, max_rows=50)
        else:
            st.info(err or "No rejected opportunities found.")
