"""
Base data source abstraction for the backtesting engine.

Defines the interface that all data sources must implement,
along with the Timeframe enum for bar interval classification.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import List, Optional

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

    Subclasses must implement load(). The other methods (fetch_historical,
    list_instruments, health_check) have default implementations that raise
    NotImplementedError — override them in API-backed sources.
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

    def fetch_historical(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data for a symbol.

        Override in API-backed sources (Zerodha, Upstox, etc.).

        Args:
            symbol: Trading symbol (e.g. "RELIANCE").
            timeframe: Bar timeframe.
            start: Start datetime.
            end: End datetime.

        Returns:
            DataFrame with DatetimeIndex and OHLCV columns.

        Raises:
            NotImplementedError: If the source doesn't support this.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support fetch_historical"
        )

    def fetch_live(
        self,
        symbol: str,
        timeframe: Timeframe | str | None = None,
    ) -> pd.Series:
        """Fetch latest available bar/quote for a symbol.

        Override in API-backed sources that support live or near-live quotes.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support fetch_live"
        )

    def list_instruments(self) -> List[str]:
        """List available instruments/symbols from this source.

        Override in API-backed sources.

        Returns:
            List of symbol strings.

        Raises:
            NotImplementedError: If the source doesn't support this.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support list_instruments"
        )

    def health_check(self) -> dict:
        """Check connectivity and readiness of the data source.

        Override in API-backed sources.

        Returns:
            Dict with at least {"status": "ok"|"error", "provider": "..."}.
        """
        return {
            "status": "ok",
            "provider": self.__class__.__name__,
            "message": "No health check implemented; assuming OK.",
        }
