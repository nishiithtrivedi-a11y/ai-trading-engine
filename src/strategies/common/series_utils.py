"""Shared series helpers for strategy implementations."""

from __future__ import annotations

import pandas as pd


def rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    """Rolling z-score with NaN-safe zero-std handling."""
    if window <= 1:
        raise ValueError("window must be > 1")
    mean = series.rolling(window=window, min_periods=window).mean()
    std = series.rolling(window=window, min_periods=window).std(ddof=0)
    return (series - mean) / std.replace(0.0, pd.NA)


def bollinger_bands(
    series: pd.Series,
    window: int = 20,
    num_std: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return middle, upper, lower Bollinger bands."""
    if window <= 1:
        raise ValueError("window must be > 1")
    if num_std <= 0:
        raise ValueError("num_std must be > 0")

    middle = series.rolling(window=window, min_periods=window).mean()
    std = series.rolling(window=window, min_periods=window).std(ddof=0)
    upper = middle + num_std * std
    lower = middle - num_std * std
    return middle, upper, lower


def day_session_groups(index: pd.DatetimeIndex, timezone: str) -> pd.Series:
    """Create day-level grouping keys in a target timezone."""
    ts = pd.to_datetime(index)
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    local = ts.tz_convert(timezone)
    return pd.Series(local.date, index=index)

