"""
Base data source abstraction for the backtesting engine.

Defines the interface that all data sources must implement,
along with the Timeframe enum for bar interval classification.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

import pandas as pd


class Timeframe(str, Enum):
    """Supported bar timeframes."""
    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    HOURLY = "1h"
    DAILY = "1D"


class BaseDataSource(ABC):
    """Abstract base class for all data sources.

    Implementations must return a pandas DataFrame with:
    - DatetimeIndex named "timestamp"
    - Columns: open, high, low, close, volume (lowercase)
    - Sorted chronologically
    """

    @abstractmethod
    def load(self) -> pd.DataFrame:
        """Load and return OHLCV data as a DataFrame.

        Returns:
            DataFrame with DatetimeIndex and OHLCV columns.

        Raises:
            FileNotFoundError: If the data source file doesn't exist.
            NotImplementedError: If the source is a placeholder stub.
        """
        ...
