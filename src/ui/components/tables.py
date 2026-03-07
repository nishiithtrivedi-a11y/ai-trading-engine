"""
Table display components for the Streamlit dashboard.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from src.ui.utils.formatters import clean_column_name


def data_table(
    df: pd.DataFrame,
    title: Optional[str] = None,
    max_rows: int = 100,
    rename_columns: bool = True,
    hide_index: bool = True,
) -> None:
    """Display a DataFrame as a styled table.

    Args:
        df: DataFrame to display.
        title: Optional section title.
        max_rows: Maximum rows to show.
        rename_columns: Whether to convert snake_case to Title Case.
        hide_index: Whether to hide the DataFrame index.
    """
    if title:
        st.subheader(title)

    if df is None or df.empty:
        st.info("No data available.")
        return

    display_df = df.head(max_rows).copy()
    if rename_columns:
        display_df.columns = [clean_column_name(c) for c in display_df.columns]

    st.dataframe(display_df, use_container_width=True, hide_index=hide_index)

    if len(df) > max_rows:
        st.caption(f"Showing {max_rows} of {len(df)} rows")


def trade_log_table(df: pd.DataFrame, title: str = "Trade Log") -> None:
    """Display a trade log with key columns highlighted."""
    if df is None or df.empty:
        st.info("No trades recorded.")
        return

    st.subheader(title)

    # Select key columns if available
    preferred = [
        "symbol", "entry_price", "exit_price", "quantity",
        "gross_pnl", "net_pnl", "return_pct", "fees",
        "bars_held", "reason", "entry_timestamp", "exit_timestamp",
    ]
    available = [c for c in preferred if c in df.columns]
    display_df = df[available] if available else df

    display_df = display_df.copy()
    display_df.columns = [clean_column_name(c) for c in display_df.columns]

    st.dataframe(display_df, use_container_width=True, hide_index=True)
    st.caption(f"{len(df)} total trades")


def opportunities_table(
    df: pd.DataFrame,
    title: str = "Opportunities",
    max_rows: int = 50,
) -> None:
    """Display scanner/decision opportunities table."""
    if df is None or df.empty:
        st.info("No opportunities found.")
        return

    st.subheader(title)

    preferred = [
        "symbol", "timeframe", "strategy_name", "signal",
        "classification", "entry_price", "stop_loss", "target_price",
        "score", "rank",
    ]
    available = [c for c in preferred if c in df.columns]
    display_df = df[available].head(max_rows) if available else df.head(max_rows)

    display_df = display_df.copy()
    display_df.columns = [clean_column_name(c) for c in display_df.columns]

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    if len(df) > max_rows:
        st.caption(f"Showing {max_rows} of {len(df)} rows")


def picks_table(
    df: pd.DataFrame,
    title: str = "Top Picks",
    max_rows: int = 20,
) -> None:
    """Display decision engine picks."""
    if df is None or df.empty:
        st.info("No picks available.")
        return

    st.subheader(title)

    preferred = [
        "symbol", "timeframe", "strategy_name", "horizon",
        "entry_price", "stop_loss", "target_price", "risk_reward",
        "conviction_score", "priority_rank",
    ]
    available = [c for c in preferred if c in df.columns]
    display_df = df[available].head(max_rows) if available else df.head(max_rows)

    display_df = display_df.copy()
    display_df.columns = [clean_column_name(c) for c in display_df.columns]

    st.dataframe(display_df, use_container_width=True, hide_index=True)


def alerts_table(
    df: pd.DataFrame,
    title: str = "Alerts",
    max_rows: int = 50,
) -> None:
    """Display alerts table."""
    if df is None or df.empty:
        st.info("No alerts generated.")
        return

    st.subheader(title)

    preferred = [
        "severity", "title", "message", "symbol", "timestamp",
    ]
    available = [c for c in preferred if c in df.columns]
    display_df = df[available].head(max_rows) if available else df.head(max_rows)

    display_df = display_df.copy()
    display_df.columns = [clean_column_name(c) for c in display_df.columns]

    st.dataframe(display_df, use_container_width=True, hide_index=True)


def key_value_table(data: Dict[str, Any], title: Optional[str] = None) -> None:
    """Display a dict as a two-column key-value table."""
    if title:
        st.subheader(title)
    if not data:
        st.info("No data available.")
        return

    rows = [
        {"Field": clean_column_name(str(k)), "Value": str(v)}
        for k, v in data.items()
        if v is not None
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
