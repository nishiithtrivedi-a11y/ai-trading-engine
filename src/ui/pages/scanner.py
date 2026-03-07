"""
Scanner page - view latest ranked opportunities from the stock scanner.
"""

from __future__ import annotations

import streamlit as st

from src.ui.components.filters import score_range_filter, apply_score_filter, symbol_filter, top_n_selector
from src.ui.components.tables import opportunities_table, data_table
from src.ui.utils.loaders import load_scanner_opportunities, load_scanner_json
from src.ui.utils.formatters import fmt_timestamp


def render(output_dir: str) -> None:
    st.header("Scanner - Ranked Opportunities")

    df, err = load_scanner_opportunities(output_dir)

    if df is None:
        st.info(
            f"{err}\n\n"
            "Run the scanner engine to generate opportunities. "
            "See the README for scanner usage examples."
        )
        return

    # Metadata from JSON
    json_data, _ = load_scanner_json(output_dir)
    if json_data:
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            st.metric("Symbols Scanned", json_data.get("num_symbols_scanned", "N/A"))
        with mc2:
            st.metric("Total Opportunities", json_data.get("num_opportunities", len(df)))
        with mc3:
            st.metric("Generated At", fmt_timestamp(json_data.get("generated_at")))
        st.divider()

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        top_n = top_n_selector(key="scanner_top_n")
    with col2:
        min_score = score_range_filter(key="scanner_min_score")

    filtered = apply_score_filter(df, min_score)
    filtered = symbol_filter(filtered, key="scanner_symbol_filter")

    # Sort by score/rank
    if "score" in filtered.columns:
        filtered = filtered.sort_values("score", ascending=False)
    elif "rank" in filtered.columns:
        filtered = filtered.sort_values("rank")

    opportunities_table(filtered, title="Opportunities", max_rows=top_n)

    # Score breakdown
    score_cols = [c for c in df.columns if c.startswith("score_")]
    if score_cols and not filtered.empty:
        st.divider()
        st.subheader("Score Components")
        st.dataframe(
            filtered[["symbol"] + score_cols].head(top_n) if "symbol" in filtered.columns
            else filtered[score_cols].head(top_n),
            use_container_width=True,
            hide_index=True,
        )

    # Classification distribution
    if "classification" in df.columns:
        st.divider()
        st.subheader("Classification Distribution")
        dist = df["classification"].value_counts()
        st.bar_chart(dist)
