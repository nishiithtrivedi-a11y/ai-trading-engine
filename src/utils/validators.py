"""
Data validation utilities for the backtesting engine.

Validates OHLCV data integrity before backtesting begins.
"""

from __future__ import annotations

import pandas as pd

from src.utils.logger import setup_logger

logger = setup_logger("validators")


REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}


class DataValidationError(Exception):
    """Raised when market data fails validation."""
    pass


def validate_ohlcv_dataframe(df: pd.DataFrame) -> list[str]:
    """Validate an OHLCV DataFrame and return a list of warnings.

    Raises DataValidationError for critical issues that prevent backtesting.
    Returns a list of non-critical warnings.

    Args:
        df: DataFrame with OHLCV data. Index should be DatetimeIndex.

    Returns:
        List of warning messages for non-critical issues.
    """
    warnings: list[str] = []

    if df.empty:
        raise DataValidationError("DataFrame is empty")

    # Check required columns
    missing_cols = REQUIRED_COLUMNS - set(df.columns)
    if missing_cols:
        raise DataValidationError(f"Missing required columns: {missing_cols}")

    # Check index is DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        raise DataValidationError(
            f"Index must be DatetimeIndex, got {type(df.index).__name__}"
        )

    # Check for duplicate timestamps
    duplicates = df.index.duplicated()
    if duplicates.any():
        n_dupes = duplicates.sum()
        raise DataValidationError(
            f"Found {n_dupes} duplicate timestamp(s). Remove duplicates before backtesting."
        )

    # Check chronological order
    if not df.index.is_monotonic_increasing:
        warnings.append("Data is not sorted chronologically. It will be sorted automatically.")

    # Check for negative prices
    price_cols = ["open", "high", "low", "close"]
    for col in price_cols:
        if (df[col] <= 0).any():
            n_invalid = (df[col] <= 0).sum()
            raise DataValidationError(
                f"Column '{col}' has {n_invalid} non-positive value(s)"
            )

    # Check OHLC consistency: high >= low
    bad_hl = df["high"] < df["low"]
    if bad_hl.any():
        n_bad = bad_hl.sum()
        raise DataValidationError(
            f"Found {n_bad} bar(s) where high < low"
        )

    # Check OHLC consistency: high >= open and high >= close
    bad_ho = df["high"] < df["open"]
    bad_hc = df["high"] < df["close"]
    if bad_ho.any() or bad_hc.any():
        n_bad = bad_ho.sum() + bad_hc.sum()
        warnings.append(f"Found {n_bad} bar(s) where high < open or high < close")

    # Check OHLC consistency: low <= open and low <= close
    bad_lo = df["low"] > df["open"]
    bad_lc = df["low"] > df["close"]
    if bad_lo.any() or bad_lc.any():
        n_bad = bad_lo.sum() + bad_lc.sum()
        warnings.append(f"Found {n_bad} bar(s) where low > open or low > close")

    # Check for negative volume
    if (df["volume"] < 0).any():
        n_neg = (df["volume"] < 0).sum()
        raise DataValidationError(
            f"Column 'volume' has {n_neg} negative value(s)"
        )

    # Check for zero-volume bars
    zero_vol = (df["volume"] == 0).sum()
    if zero_vol > 0:
        warnings.append(f"Found {zero_vol} zero-volume bar(s)")

    # Check for NaN values in price columns
    for col in price_cols:
        n_nan = df[col].isna().sum()
        if n_nan > 0:
            warnings.append(f"Column '{col}' has {n_nan} NaN value(s) that will be forward-filled")

    return warnings
