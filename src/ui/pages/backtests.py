"""
Backtests page - view backtest results, equity curves, and trade logs.
"""

from __future__ import annotations

import streamlit as st

from src.ui.components.charts import drawdown_chart, equity_curve_chart
from src.ui.components.filters import backtest_run_selector
from src.ui.components.metrics_cards import backtest_summary_cards
from src.ui.components.tables import data_table, trade_log_table
from src.ui.utils.loaders import (
    list_backtest_runs,
    load_backtest_equity_curve,
    load_backtest_metrics,
    load_backtest_trade_log,
)


def render(output_dir: str) -> None:
    st.header("Backtest Results")

    runs = list_backtest_runs(output_dir)
    if not runs:
        st.info(
            "No backtest output found. Run a backtest first to see results here.\n\n"
            "Example: `python main.py` or `python run_multi_asset_backtest.py`"
        )
        return

    selected = backtest_run_selector(runs, key="bt_run_selector")
    if not selected:
        return

    st.divider()

    # Metrics
    metrics, metrics_err = load_backtest_metrics(selected, output_dir)
    if metrics:
        st.subheader("Performance Summary")
        backtest_summary_cards(metrics)
    else:
        st.info(f"No metrics JSON found for '{selected}'. Metrics display requires a metrics.json export.")

    st.divider()

    # Equity curve
    eq_df, eq_err = load_backtest_equity_curve(selected, output_dir)
    if eq_df is not None:
        equity_curve_chart(eq_df, title="Equity Curve")
        drawdown_chart(eq_df, title="Drawdown")
    else:
        st.info(eq_err or "No equity curve data available.")

    st.divider()

    # Trade log
    trades_df, trades_err = load_backtest_trade_log(selected, output_dir)
    if trades_df is not None:
        trade_log_table(trades_df)
    else:
        st.info(trades_err or "No trade log available.")
