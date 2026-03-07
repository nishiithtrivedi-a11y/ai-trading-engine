"""
Metric card components for the Streamlit dashboard.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from src.ui.utils.formatters import (
    color_pnl,
    fmt_currency,
    fmt_number,
    fmt_pct,
    fmt_ratio,
)


def metric_card(
    label: str,
    value: str,
    delta: Optional[str] = None,
    delta_color: str = "normal",
) -> None:
    """Render a single Streamlit metric card."""
    st.metric(label=label, value=value, delta=delta, delta_color=delta_color)


def metrics_row(metrics: Dict[str, Any], layout: List[Tuple[str, str]]) -> None:
    """Render a row of metric cards.

    Args:
        metrics: Raw metrics dict.
        layout: List of (key, display_label) tuples.
    """
    cols = st.columns(len(layout))
    formatters = {
        "sharpe_ratio": fmt_ratio,
        "sortino_ratio": fmt_ratio,
        "profit_factor": fmt_ratio,
        "total_return_pct": fmt_pct,
        "annualized_return": fmt_pct,
        "cagr": fmt_pct,
        "max_drawdown_pct": fmt_pct,
        "win_rate": fmt_pct,
        "final_value": lambda v: fmt_currency(v, decimals=0),
        "num_trades": lambda v: fmt_number(v, decimals=0),
        "total_fees": lambda v: fmt_currency(v, decimals=2),
    }

    for col, (key, label) in zip(cols, layout):
        val = metrics.get(key)
        formatter = formatters.get(key, lambda v: fmt_number(v))
        with col:
            st.metric(label=label, value=formatter(val))


def backtest_summary_cards(metrics: Dict[str, Any]) -> None:
    """Render standard backtest summary metrics."""
    row1 = [
        ("final_value", "Final Value"),
        ("total_return_pct", "Total Return"),
        ("sharpe_ratio", "Sharpe Ratio"),
        ("max_drawdown_pct", "Max Drawdown"),
    ]
    row2 = [
        ("num_trades", "Trades"),
        ("win_rate", "Win Rate"),
        ("profit_factor", "Profit Factor"),
        ("sortino_ratio", "Sortino Ratio"),
    ]
    metrics_row(metrics, row1)
    metrics_row(metrics, row2)


def availability_cards(availability: Dict[str, bool]) -> None:
    """Show data availability status for each phase."""
    cols = st.columns(len(availability))
    for col, (phase, available) in zip(cols, availability.items()):
        with col:
            status = "Available" if available else "No data"
            icon = ":" if available else ":"
            st.metric(
                label=phase.replace("_", " ").title(),
                value=status,
            )
