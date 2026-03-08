"""
Optimization page - view strategy ranking and parameter optimization results.
"""

from __future__ import annotations

import streamlit as st

from src.ui.components.filters import backtest_run_selector, top_n_selector
from src.ui.components.tables import data_table
from src.ui.utils.loaders import list_backtest_runs, load_optimization_results
from src.ui.utils.formatters import clean_column_name


def render(output_dir: str) -> None:
    st.header("Strategy Optimization")

    # Look for strategy ranking / optimization output dirs
    runs = list_backtest_runs(output_dir)
    opt_runs = [r for r in runs if any(
        k in r.lower() for k in ["optim", "ranking", "strategy_ranking"]
    )]

    if not opt_runs and runs:
        opt_runs = runs  # Fall back to showing all runs

    if not opt_runs:
        st.info(
            "No optimization output found. Run the strategy ranking first.\n\n"
            "Example: `python run_strategy_ranking.py data/RELIANCE_1D.csv 10`"
        )
        return

    selected = backtest_run_selector(opt_runs, key="opt_run_selector")
    if not selected:
        return

    st.divider()

    df, err = load_optimization_results(selected, output_dir)
    if df is None:
        st.info(err or "No optimization results found.")
        return

    # Filters
    col1, col2 = st.columns([1, 3])
    with col1:
        top_n = top_n_selector(key="opt_top_n")

    st.subheader(f"Top {top_n} Strategy Rankings")
    display_df = df.head(top_n)

    # Sort by rank if available
    if "rank" in display_df.columns:
        display_df = display_df.sort_values("rank")

    data_table(display_df, max_rows=top_n)

    # Show score distribution if sharpe_ratio is present
    if "sharpe_ratio" in df.columns:
        st.divider()
        st.subheader("Sharpe Ratio Distribution")
        st.bar_chart(df["sharpe_ratio"].dropna().head(top_n))

    # Parameter analysis
    param_cols = [c for c in df.columns if c.startswith("param_")]
    if param_cols:
        st.divider()
        st.subheader("Parameter Values")
        st.dataframe(
            df[["strategy_name"] + param_cols + ["sharpe_ratio"]].head(top_n)
            if "strategy_name" in df.columns and "sharpe_ratio" in df.columns
            else df[param_cols].head(top_n),
            use_container_width=True,
            hide_index=True,
        )


if __name__ == "__main__":
    from src.ui.utils.state import get_app_state

    render(get_app_state().get_output_dir())
