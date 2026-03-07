"""
Chart components for the Streamlit dashboard.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st


def equity_curve_chart(
    df: pd.DataFrame,
    title: str = "Equity Curve",
    value_col: str = "equity",
    time_col: Optional[str] = None,
) -> None:
    """Plot an equity curve line chart.

    Args:
        df: DataFrame with equity values.
        title: Chart title.
        value_col: Column name for equity values.
        time_col: Column name for timestamps (uses index if None).
    """
    st.subheader(title)

    if df is None or df.empty:
        st.info("No equity curve data available.")
        return

    # Prepare chart data
    chart_df = df.copy()

    # Try to find the equity column
    if value_col not in chart_df.columns:
        # Try common alternatives
        for alt in ["equity", "portfolio_value", "value", "close"]:
            if alt in chart_df.columns:
                value_col = alt
                break
        else:
            st.warning(f"Column '{value_col}' not found in data.")
            return

    # Handle time column
    if time_col and time_col in chart_df.columns:
        chart_df = chart_df.set_index(time_col)
    elif "timestamp" in chart_df.columns:
        chart_df["timestamp"] = pd.to_datetime(chart_df["timestamp"])
        chart_df = chart_df.set_index("timestamp")

    st.line_chart(chart_df[[value_col]], use_container_width=True)


def drawdown_chart(
    df: pd.DataFrame,
    title: str = "Drawdown",
    dd_col: str = "drawdown_pct",
) -> None:
    """Plot a drawdown area chart."""
    st.subheader(title)

    if df is None or df.empty:
        st.info("No drawdown data available.")
        return

    chart_df = df.copy()

    if dd_col not in chart_df.columns:
        for alt in ["drawdown_pct", "drawdown", "dd"]:
            if alt in chart_df.columns:
                dd_col = alt
                break
        else:
            # Compute drawdown from equity if available
            eq_col = None
            for c in ["equity", "portfolio_value", "value"]:
                if c in chart_df.columns:
                    eq_col = c
                    break
            if eq_col:
                peak = chart_df[eq_col].cummax()
                chart_df["drawdown_pct"] = (chart_df[eq_col] - peak) / peak
                dd_col = "drawdown_pct"
            else:
                st.warning("No drawdown data available.")
                return

    if "timestamp" in chart_df.columns:
        chart_df["timestamp"] = pd.to_datetime(chart_df["timestamp"])
        chart_df = chart_df.set_index("timestamp")

    st.area_chart(chart_df[[dd_col]], use_container_width=True)


def bar_chart_from_dict(
    data: Dict[str, float],
    title: str = "",
    horizontal: bool = False,
) -> None:
    """Render a bar chart from a simple dict."""
    if not data:
        st.info("No data available.")
        return

    if title:
        st.subheader(title)

    df = pd.DataFrame(
        {"Category": list(data.keys()), "Value": list(data.values())}
    ).set_index("Category")

    st.bar_chart(df, use_container_width=True)


def score_breakdown_chart(
    breakdown: Dict[str, float],
    title: str = "Score Breakdown",
) -> None:
    """Render a horizontal bar chart showing score component breakdown."""
    if not breakdown:
        st.info("No score breakdown available.")
        return

    st.subheader(title)
    df = pd.DataFrame(
        {"Component": list(breakdown.keys()), "Score": list(breakdown.values())}
    ).set_index("Component")

    st.bar_chart(df, use_container_width=True)
