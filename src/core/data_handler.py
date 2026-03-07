"""
Market data loading and management for the backtesting engine.

Handles CSV loading, timestamp parsing, validation, cleaning,
and provides bar-by-bar data access with lookback windows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from src.utils.logger import setup_logger
from src.utils.validators import validate_ohlcv_dataframe, DataValidationError

logger = setup_logger("data_handler")


class DataHandler:
    """Loads, validates, and serves OHLCV market data.

    The DataHandler ensures that strategies can only access data up to
    the current bar index, preventing lookahead bias.

    Attributes:
        data: The full validated OHLCV DataFrame.
        current_index: The current bar position in the iteration.
    """

    def __init__(self, data: Optional[pd.DataFrame] = None) -> None:
        self._data: Optional[pd.DataFrame] = None
        self._current_index: int = 0

        if data is not None:
            self.set_data(data)

    @classmethod
    def from_source(cls, source) -> DataHandler:
        """Load data from any BaseDataSource implementation.

        Args:
            source: A BaseDataSource instance (e.g., IndianCSVDataSource).

        Returns:
            DataHandler instance with loaded and validated data.
        """
        df = source.load()
        handler = cls()
        handler.set_data(df)
        return handler

    @classmethod
    def from_csv(
        cls,
        file_path: str,
        timestamp_col: str = "timestamp",
        datetime_format: Optional[str] = None,
    ) -> DataHandler:
        """Load OHLCV data from a CSV file.

        Args:
            file_path: Path to the CSV file.
            timestamp_col: Name of the timestamp column.
            datetime_format: Optional strftime format for parsing timestamps.

        Returns:
            DataHandler instance with loaded and validated data.

        Raises:
            FileNotFoundError: If the CSV file doesn't exist.
            DataValidationError: If the data fails validation.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Data file not found: {file_path}")

        logger.info(f"Loading data from {file_path}")

        df = pd.read_csv(file_path)

        # Normalize column names to lowercase
        df.columns = df.columns.str.lower().str.strip()

        # Find and parse timestamp column
        ts_col = timestamp_col.lower().strip()
        if ts_col not in df.columns:
            # Try common alternatives
            alternatives = ["datetime", "date", "time", "ts"]
            found = False
            for alt in alternatives:
                if alt in df.columns:
                    ts_col = alt
                    found = True
                    break
            if not found:
                raise DataValidationError(
                    f"Timestamp column '{timestamp_col}' not found. "
                    f"Available columns: {list(df.columns)}"
                )

        # Parse timestamps
        if datetime_format:
            df[ts_col] = pd.to_datetime(df[ts_col], format=datetime_format)
        else:
            df[ts_col] = pd.to_datetime(df[ts_col])

        df.set_index(ts_col, inplace=True)
        df.index.name = "timestamp"

        handler = cls()
        handler.set_data(df)
        return handler

    def set_data(self, df: pd.DataFrame) -> None:
        """Set and validate the data.

        Args:
            df: OHLCV DataFrame with DatetimeIndex.

        Raises:
            DataValidationError: If validation fails.
        """
        warnings = validate_ohlcv_dataframe(df)

        for w in warnings:
            logger.warning(w)

        # Sort chronologically if needed
        if not df.index.is_monotonic_increasing:
            df = df.sort_index()

        # Forward-fill NaN values in price columns
        price_cols = ["open", "high", "low", "close"]
        for col in price_cols:
            if df[col].isna().any():
                df[col] = df[col].ffill()
                # If first rows are NaN after ffill, backfill them
                if df[col].isna().any():
                    df[col] = df[col].bfill()

        # Fill NaN volume with 0
        if "volume" in df.columns and df["volume"].isna().any():
            df["volume"] = df["volume"].fillna(0)

        self._data = df.copy()
        self._current_index = 0

        logger.info(
            f"Data loaded: {len(df)} bars from {df.index[0]} to {df.index[-1]}"
        )

    @property
    def data(self) -> pd.DataFrame:
        """Full dataset (read-only access)."""
        if self._data is None:
            raise RuntimeError("No data loaded")
        return self._data

    @property
    def current_index(self) -> int:
        return self._current_index

    @current_index.setter
    def current_index(self, value: int) -> None:
        if value < 0 or value >= len(self.data):
            raise IndexError(f"Index {value} out of range [0, {len(self.data) - 1}]")
        self._current_index = value

    def __len__(self) -> int:
        return len(self.data) if self._data is not None else 0

    def get_current_bar(self) -> pd.Series:
        """Get the current bar's OHLCV data."""
        return self.data.iloc[self._current_index]

    def get_bar(self, index: int) -> pd.Series:
        """Get a specific bar by index."""
        if index < 0 or index >= len(self.data):
            raise IndexError(f"Bar index {index} out of range")
        return self.data.iloc[index]

    def get_lookback(self, lookback: int) -> pd.DataFrame:
        """Get a window of bars ending at the current bar (inclusive).

        This is the primary method strategies should use to access data.
        It prevents lookahead bias by only returning bars up to and
        including the current bar.

        Args:
            lookback: Number of bars to include (including current bar).

        Returns:
            DataFrame slice of at most `lookback` bars.
        """
        start = max(0, self._current_index - lookback + 1)
        end = self._current_index + 1
        return self.data.iloc[start:end]

    def get_data_up_to_current(self) -> pd.DataFrame:
        """Get all data from start up to and including the current bar.

        Use this when the strategy needs the full history available so far.
        """
        return self.data.iloc[: self._current_index + 1]

    def get_current_timestamp(self) -> pd.Timestamp:
        """Get the timestamp of the current bar."""
        return self.data.index[self._current_index]

    def has_next(self) -> bool:
        """Check if there are more bars to process."""
        return self._current_index < len(self.data) - 1

    def advance(self) -> bool:
        """Move to the next bar.

        Returns:
            True if advanced, False if at end of data.
        """
        if self.has_next():
            self._current_index += 1
            return True
        return False

    def reset(self) -> None:
        """Reset the iterator to the beginning."""
        self._current_index = 0
