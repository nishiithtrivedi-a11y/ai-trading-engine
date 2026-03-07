"""
Indian market CSV data loader.

Handles CSV files from Indian market data providers (Zerodha, Upstox, etc.)
with proper timezone handling (Asia/Kolkata), timeframe auto-detection,
and NSE trading session validation.
"""

from __future__ import annotations

from datetime import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.data.base import BaseDataSource, Timeframe
from src.utils.logger import setup_logger

logger = setup_logger("indian_data_loader")

# NSE trading session hours (IST)
NSE_OPEN = time(9, 15)
NSE_CLOSE = time(15, 30)

# IST timezone string
IST = "Asia/Kolkata"

# Median interval (in minutes) to Timeframe mapping
_INTERVAL_MAP = {
    1: Timeframe.MINUTE_1,
    5: Timeframe.MINUTE_5,
    15: Timeframe.MINUTE_15,
    60: Timeframe.HOURLY,
}


class IndianCSVDataSource(BaseDataSource):
    """Loads OHLCV data from Indian market CSV files.

    Features:
    - Auto-detects and normalizes column names
    - Parses common Indian date formats (DD-MM-YYYY, DD/MM/YYYY, etc.)
    - Normalizes timestamps to Asia/Kolkata timezone
    - Auto-detects bar timeframe (1m, 5m, 15m, 1h, 1D)
    - Validates bars against NSE trading session hours (advisory)

    Args:
        file_path: Path to the CSV file.
        timezone: Target timezone (default: Asia/Kolkata).
    """

    def __init__(self, file_path: str, timezone: str = IST) -> None:
        self.file_path = file_path
        self.timezone = timezone
        self.detected_timeframe: Optional[Timeframe] = None

    def load(self) -> pd.DataFrame:
        """Load, parse, and normalize Indian market CSV data.

        Returns:
            DataFrame with DatetimeIndex (timezone-aware, IST) and OHLCV columns.

        Raises:
            FileNotFoundError: If the CSV file doesn't exist.
        """
        path = Path(self.file_path)
        if not path.exists():
            raise FileNotFoundError(f"Data file not found: {self.file_path}")

        logger.info(f"Loading Indian market data from {self.file_path}")

        df = pd.read_csv(self.file_path)
        df = self._normalize_column_names(df)

        ts_col = self._find_timestamp_column(df)
        df = self._parse_timestamps(df, ts_col)

        # Set timestamp as index
        df.set_index(ts_col, inplace=True)
        df.index.name = "timestamp"

        # Normalize timezone
        df.index = self._normalize_timezone(df.index)

        # Sort chronologically
        if not df.index.is_monotonic_increasing:
            df = df.sort_index()

        # Detect timeframe
        self.detected_timeframe = self._detect_timeframe(df.index)
        logger.info(f"Detected timeframe: {self.detected_timeframe.value}")

        # Validate trading session (advisory only)
        self._validate_trading_session(df, self.detected_timeframe)

        logger.info(
            f"Loaded {len(df)} bars from {df.index[0]} to {df.index[-1]}"
        )

        return df

    def _normalize_column_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names to lowercase standard format.

        Handles common variants from Indian data providers:
        - "Date", "DateTime", "Datetime" → kept for timestamp detection
        - "Open", "OPEN" → "open"
        - "High", "HIGH" → "high"
        - "Low", "LOW" → "low"
        - "Close", "CLOSE", "LTP" → "close"
        - "Volume", "VOLUME", "Traded Qty" → "volume"
        """
        df.columns = df.columns.str.strip()

        rename_map = {}
        for col in df.columns:
            lower = col.lower().strip()

            if lower in ("open", "high", "low", "close", "volume"):
                rename_map[col] = lower
            elif lower == "ltp":
                rename_map[col] = "close"
            elif lower in ("traded qty", "traded_qty", "tradedqty"):
                rename_map[col] = "volume"
            elif lower in ("timestamp", "datetime", "date", "time", "ts"):
                rename_map[col] = lower
            else:
                rename_map[col] = lower

        df = df.rename(columns=rename_map)
        return df

    def _find_timestamp_column(self, df: pd.DataFrame) -> str:
        """Find the timestamp column in the DataFrame.

        Searches for common timestamp column names used by Indian
        data providers.

        Returns:
            Name of the timestamp column.

        Raises:
            ValueError: If no timestamp column is found.
        """
        candidates = ["timestamp", "datetime", "date", "time", "ts"]

        for name in candidates:
            if name in df.columns:
                return name

        raise ValueError(
            f"No timestamp column found. Available columns: {list(df.columns)}. "
            f"Expected one of: {candidates}"
        )

    def _parse_timestamps(
        self, df: pd.DataFrame, ts_col: str
    ) -> pd.DataFrame:
        """Parse timestamp column with common Indian date formats.

        Tries pandas auto-parsing first, then falls back to explicit
        formats commonly used by Indian data providers.
        """
        try:
            df[ts_col] = pd.to_datetime(df[ts_col], dayfirst=True)
        except (ValueError, TypeError):
            # Try common Indian formats
            indian_formats = [
                "%d-%m-%Y %H:%M:%S",
                "%d-%m-%Y %H:%M",
                "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M",
                "%d-%m-%Y",
                "%d/%m/%Y",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
            ]

            parsed = False
            for fmt in indian_formats:
                try:
                    df[ts_col] = pd.to_datetime(df[ts_col], format=fmt)
                    logger.info(f"Parsed timestamps with format: {fmt}")
                    parsed = True
                    break
                except (ValueError, TypeError):
                    continue

            if not parsed:
                raise ValueError(
                    f"Could not parse timestamps in column '{ts_col}'. "
                    f"Tried formats: {indian_formats}"
                )

        return df

    def _normalize_timezone(self, index: pd.DatetimeIndex) -> pd.DatetimeIndex:
        """Normalize DatetimeIndex to IST (Asia/Kolkata).

        Three cases:
        1. Naive (no timezone) → localize to IST
        2. Non-IST aware → convert to IST
        3. Already IST → no-op
        """
        if index.tz is None:
            # Case 1: Naive timestamps — assume they're already in IST
            logger.info("Localizing naive timestamps to IST")
            return index.tz_localize(self.timezone)
        elif str(index.tz) != IST:
            # Case 2: Different timezone — convert to IST
            logger.info(f"Converting timestamps from {index.tz} to IST")
            return index.tz_convert(self.timezone)
        else:
            # Case 3: Already IST
            return index

    def _detect_timeframe(self, index: pd.DatetimeIndex) -> Timeframe:
        """Auto-detect bar timeframe from median timestamp interval.

        Computes the median time difference between consecutive bars
        and maps it to the nearest Timeframe enum value.

        Returns:
            Detected Timeframe.
        """
        if len(index) < 2:
            logger.warning("Not enough bars to detect timeframe, defaulting to DAILY")
            return Timeframe.DAILY

        diffs = pd.Series(index).diff().dropna()
        median_diff = diffs.median()
        median_minutes = median_diff.total_seconds() / 60

        # Map to nearest known interval
        for interval_minutes, timeframe in sorted(_INTERVAL_MAP.items()):
            if median_minutes <= interval_minutes * 1.5:
                return timeframe

        # If median > 90 minutes, it's daily
        return Timeframe.DAILY

    def _validate_trading_session(
        self, df: pd.DataFrame, timeframe: Timeframe
    ) -> None:
        """Validate that intraday bars fall within NSE trading hours.

        For intraday timeframes only (not daily). Issues warnings
        for bars outside the 9:15–15:30 IST session. Does not
        reject or filter data.
        """
        if timeframe == Timeframe.DAILY:
            return

        times = df.index.time
        before_open = sum(1 for t in times if t < NSE_OPEN)
        after_close = sum(1 for t in times if t > NSE_CLOSE)
        total_outside = before_open + after_close

        if total_outside > 0:
            pct = total_outside / len(df) * 100
            logger.warning(
                f"{total_outside} bars ({pct:.1f}%) fall outside NSE session "
                f"hours ({NSE_OPEN}–{NSE_CLOSE} IST). "
                f"Before open: {before_open}, After close: {after_close}"
            )
        else:
            logger.info("All bars within NSE trading session hours")
