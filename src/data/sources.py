"""
Placeholder data source implementations for Indian broker APIs.

These are stubs that define the interface for future integration
with Zerodha (KiteConnect) and Upstox APIs. They raise
NotImplementedError when load() is called.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from src.data.base import BaseDataSource, Timeframe
from src.utils.logger import setup_logger

logger = setup_logger("data_sources")


class ZerodhaDataSource(BaseDataSource):
    """Placeholder for Zerodha KiteConnect data integration.

    Requires the `kiteconnect` package and valid API credentials.
    See: https://kite.trade/docs/connect/v3/

    Args:
        api_key: Zerodha API key.
        api_secret: Zerodha API secret.
        access_token: Session access token.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        access_token: str,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token

    def load(self) -> pd.DataFrame:
        """Not implemented — requires kiteconnect package.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "Zerodha integration requires the 'kiteconnect' package. "
            "Install with: pip install kiteconnect. "
            "See https://kite.trade/docs/connect/v3/ for API setup."
        )

    def fetch_historical(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data from Zerodha.

        Placeholder for future implementation.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE", "NIFTY 50").
            timeframe: Bar timeframe.
            start: Start datetime.
            end: End datetime.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("Zerodha historical data fetch not yet implemented")

    def fetch_live(self, symbol: str) -> pd.Series:
        """Fetch live tick data from Zerodha.

        Placeholder for future implementation.

        Args:
            symbol: Trading symbol.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("Zerodha live data fetch not yet implemented")


class UpstoxDataSource(BaseDataSource):
    """Placeholder for Upstox API data integration.

    Requires the `upstox-python-sdk` package and valid API credentials.
    See: https://upstox.com/developer/api-documentation/

    Args:
        api_key: Upstox API key.
        api_secret: Upstox API secret.
        access_token: Session access token.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        access_token: str,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token

    def load(self) -> pd.DataFrame:
        """Not implemented — requires upstox-python-sdk package.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "Upstox integration requires the 'upstox-python-sdk' package. "
            "Install with: pip install upstox-python-sdk. "
            "See https://upstox.com/developer/api-documentation/ for API setup."
        )

    def fetch_historical(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data from Upstox.

        Placeholder for future implementation.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE", "NIFTY50").
            timeframe: Bar timeframe.
            start: Start datetime.
            end: End datetime.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("Upstox historical data fetch not yet implemented")

    def fetch_live(self, symbol: str) -> pd.Series:
        """Fetch live tick data from Upstox.

        Placeholder for future implementation.

        Args:
            symbol: Trading symbol.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("Upstox live data fetch not yet implemented")
