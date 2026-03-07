"""
Filter components for the Streamlit dashboard.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pandas as pd
import streamlit as st


def symbol_filter(
    df: pd.DataFrame,
    col: str = "symbol",
    label: str = "Filter by Symbol",
    key: Optional[str] = None,
) -> pd.DataFrame:
    """Add a multi-select symbol filter and return filtered DataFrame."""
    if df is None or df.empty or col not in df.columns:
        return df

    symbols = sorted(df[col].dropna().unique().tolist())
    selected = st.multiselect(label, symbols, default=[], key=key)
    if selected:
        return df[df[col].isin(selected)]
    return df


def horizon_filter(
    key: str = "horizon_filter",
) -> str:
    """Render a horizon selector and return selected value."""
    options = ["intraday", "swing", "positional"]
    return st.selectbox("Horizon", options, key=key)


def score_range_filter(
    label: str = "Minimum Score",
    min_val: float = 0.0,
    max_val: float = 100.0,
    default: float = 0.0,
    key: Optional[str] = None,
) -> float:
    """Render a score slider filter."""
    return st.slider(label, min_val, max_val, default, key=key)


def apply_score_filter(
    df: pd.DataFrame,
    min_score: float,
    col: str = "score",
) -> pd.DataFrame:
    """Filter a DataFrame by minimum score."""
    if df is None or df.empty or col not in df.columns:
        return df
    return df[df[col] >= min_score]


def severity_filter(
    df: pd.DataFrame,
    col: str = "severity",
    key: Optional[str] = None,
) -> pd.DataFrame:
    """Add a severity filter for alerts."""
    if df is None or df.empty or col not in df.columns:
        return df

    severities = sorted(df[col].dropna().unique().tolist())
    selected = st.multiselect("Filter by Severity", severities, default=[], key=key)
    if selected:
        return df[df[col].isin(selected)]
    return df


def backtest_run_selector(
    runs: List[str],
    key: str = "backtest_selector",
) -> Optional[str]:
    """Render a backtest run selector dropdown."""
    if not runs:
        st.info("No backtest runs found in the output directory.")
        return None
    return st.selectbox("Select Backtest Run", runs, key=key)


def top_n_selector(
    label: str = "Show Top N",
    options: List[int] = None,
    key: Optional[str] = None,
) -> int:
    """Render a top-N selector."""
    if options is None:
        options = [5, 10, 20, 50, 100]
    return st.selectbox(label, options, index=1, key=key)
