"""
Walk-Forward page - view out-of-sample validation results.
"""

from __future__ import annotations

import streamlit as st

from src.ui.components.filters import backtest_run_selector
from src.ui.components.tables import data_table, key_value_table
from src.ui.utils.loaders import (
    list_backtest_runs,
    load_walk_forward_results,
    load_walk_forward_summary,
)


def render(output_dir: str) -> None:
    st.header("Walk-Forward Analysis")

    runs = list_backtest_runs(output_dir)
    wf_runs = [r for r in runs if any(
        k in r.lower() for k in ["walk", "wf", "walkforward"]
    )]

    if not wf_runs and runs:
        wf_runs = runs

    if not wf_runs:
        st.info(
            "No walk-forward output found. Run walk-forward analysis first.\n\n"
            "Example: `python run_rsi_walkforward.py`"
        )
        return

    selected = backtest_run_selector(wf_runs, key="wf_run_selector")
    if not selected:
        return

    st.divider()

    # Summary
    summary, sum_err = load_walk_forward_summary(selected, output_dir)
    if summary:
        st.subheader("Aggregate Summary")

        agg = summary.get("aggregate_metrics", summary)
        key_metrics = {}
        for k, v in agg.items():
            if isinstance(v, (int, float, str)):
                key_metrics[k] = v

        if key_metrics:
            cols = st.columns(min(4, len(key_metrics)))
            items = list(key_metrics.items())
            for i, (k, v) in enumerate(items[:4]):
                with cols[i]:
                    label = k.replace("_", " ").title()
                    st.metric(label, f"{v:.4f}" if isinstance(v, float) else str(v))

            if len(items) > 4:
                key_value_table(dict(items[4:]))

    st.divider()

    # Per-window results
    df, err = load_walk_forward_results(selected, output_dir)
    if df is not None:
        st.subheader("Per-Window Results")
        data_table(df, max_rows=50)

        # Chart: test sharpe by window
        sharpe_col = None
        for c in df.columns:
            if "test" in c.lower() and "sharpe" in c.lower():
                sharpe_col = c
                break
        if sharpe_col:
            st.subheader("Out-of-Sample Sharpe by Window")
            st.bar_chart(df[sharpe_col].dropna())
    else:
        st.info(err or "No per-window walk-forward results found.")


if __name__ == "__main__":
    from src.ui.utils.state import get_app_state

    render(get_app_state().get_output_dir())
