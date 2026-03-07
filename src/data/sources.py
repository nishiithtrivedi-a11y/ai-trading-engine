"""
Broker API data source implementations for Indian markets.

Zerodha (KiteConnect) and Upstox stubs with proper interface scaffolding.
All API methods raise NotImplementedError until real integration is added.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

import pandas as pd

from src.data.base import BaseDataSource, Timeframe
from src.utils.logger import setup_logger

logger = setup_logger("data_sources")


class ZerodhaDataSource(BaseDataSource):
    """Zerodha KiteConnect data source.

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
        raise NotImplementedError(
            "Zerodha fetch_historical not yet implemented. "
            "Requires kiteconnect: kite.historical_data(instrument_token, from_date, to_date, interval)"
        )

    def fetch_live(self, symbol: str) -> pd.Series:
        """Fetch live tick data from Zerodha (placeholder)."""
        raise NotImplementedError(
            "Zerodha fetch_live not yet implemented. "
            "Requires kiteconnect WebSocket: KiteTicker"
        )

    def list_instruments(self) -> List[str]:
        raise NotImplementedError(
            "Zerodha list_instruments not yet implemented. "
            "Requires kiteconnect: kite.instruments('NSE')"
        )

    def health_check(self) -> dict:
        """Check Zerodha API connectivity."""
        try:
            import kiteconnect  # noqa: F401
            has_package = True
        except ImportError:
            has_package = False

        creds_ok = bool(self.api_key and self.api_secret and self.access_token)

        if not has_package:
            return {
                "status": "error",
                "provider": "zerodha",
                "message": "kiteconnect package not installed",
            }
        if not creds_ok:
            return {
                "status": "error",
                "provider": "zerodha",
                "message": "Missing API credentials",
            }
        return {
            "status": "ok",
            "provider": "zerodha",
            "message": "Credentials configured (connection not tested)",
        }


class UpstoxDataSource(BaseDataSource):
    """Upstox API data source.

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
        raise NotImplementedError(
            "Upstox fetch_historical not yet implemented. "
            "Requires upstox-python-sdk: HistoryApi.get_historical_candle_data()"
        )

    def fetch_live(self, symbol: str) -> pd.Series:
        """Fetch live tick data from Upstox (placeholder)."""
        raise NotImplementedError(
            "Upstox fetch_live not yet implemented. "
            "Requires upstox-python-sdk WebSocket: MarketDataStreamer"
        )

    def list_instruments(self) -> List[str]:
        raise NotImplementedError(
            "Upstox list_instruments not yet implemented. "
            "Requires upstox-python-sdk: InstrumentApi"
        )

    def health_check(self) -> dict:
        """Check Upstox API connectivity."""
        try:
            import upstox_client  # noqa: F401
            has_package = True
        except ImportError:
            has_package = False

        creds_ok = bool(self.api_key and self.api_secret and self.access_token)

        if not has_package:
            return {
                "status": "error",
                "provider": "upstox",
                "message": "upstox-python-sdk package not installed",
            }
        if not creds_ok:
            return {
                "status": "error",
                "provider": "upstox",
                "message": "Missing API credentials",
            }
        return {
            "status": "ok",
            "provider": "upstox",
            "message": "Credentials configured (connection not tested)",
        }
