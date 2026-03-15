"""
Broker API data source implementations for Indian markets.

- ZerodhaDataSource: Fully implemented KiteConnect historical data source.
- UpstoxDataSource: Placeholder stub for future Upstox integration.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

import pandas as pd

from src.data.base import BaseDataSource, Timeframe
from src.utils.logger import setup_logger

logger = setup_logger("data_sources")

# ---------------------------------------------------------------------------
# Kite interval mapping
# ---------------------------------------------------------------------------
# Maps the engine's Timeframe enum to Kite's interval strings.
# Kite accepts: minute, 3minute, 5minute, 10minute, 15minute,
#               30minute, 60minute, day
_TIMEFRAME_TO_KITE_INTERVAL = {
    Timeframe.MINUTE_1: "minute",
    Timeframe.MINUTE_5: "5minute",
    Timeframe.MINUTE_15: "15minute",
    Timeframe.HOURLY: "60minute",
    Timeframe.DAILY: "day",
}


class ZerodhaDataSource(BaseDataSource):
    """Zerodha KiteConnect data source — fully implemented.

    Provides historical OHLCV data from Kite Connect, normalized to
    the engine's expected DataFrame schema (DatetimeIndex named
    ``"timestamp"`` + lowercase OHLCV columns).

    Requires the ``kiteconnect`` package and valid API credentials.
    See: https://kite.trade/docs/connect/v3/

    Args:
        api_key: Zerodha API key.
        api_secret: Zerodha API secret.
        access_token: Session access token.
        default_symbol: Default symbol for ``load()`` (optional).
        default_timeframe: Default timeframe for ``load()`` (optional).
        default_days: How many calendar days of history ``load()`` fetches.
        exchange: Default exchange (default: ``"NSE"``).
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        access_token: str,
        default_symbol: str = "RELIANCE",
        default_timeframe: Timeframe = Timeframe.DAILY,
        default_days: int = 365,
        exchange: str = "NSE",
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.default_symbol = default_symbol
        self.default_timeframe = default_timeframe
        self.default_days = default_days
        self.exchange = exchange

        # Lazily initialised
        self._kite = None
        self._instrument_mapper = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_kite(self):
        """Lazily create and authenticate the KiteConnect client."""
        if self._kite is None:
            from kiteconnect import KiteConnect

            self._kite = KiteConnect(api_key=self.api_key)
            self._kite.set_access_token(self.access_token)
            logger.info("KiteConnect client initialised")
        return self._kite

    def _get_mapper(self):
        """Lazily create the instrument mapper."""
        if self._instrument_mapper is None:
            from src.data.instrument_mapper import KiteInstrumentMapper

            self._instrument_mapper = KiteInstrumentMapper(
                kite=self._get_kite(),
                exchange=self.exchange,
            )
        return self._instrument_mapper

    @staticmethod
    def _kite_interval(timeframe: Timeframe) -> str:
        """Convert engine Timeframe to Kite interval string."""
        interval = _TIMEFRAME_TO_KITE_INTERVAL.get(timeframe)
        if interval is None:
            raise ValueError(
                f"Unsupported timeframe for Kite: {timeframe}. "
                f"Supported: {list(_TIMEFRAME_TO_KITE_INTERVAL.keys())}"
            )
        return interval

    def _normalize_df(self, records: list[dict]) -> pd.DataFrame:
        """Convert Kite historical_data response to engine-standard DataFrame.

        Kite returns a list of dicts with keys:
            date, open, high, low, close, volume

        Engine expects:
            DatetimeIndex named "timestamp" + lowercase OHLCV columns,
            sorted chronologically.
        """
        if not records:
            return pd.DataFrame(
                columns=["open", "high", "low", "close", "volume"]
            )

        df = pd.DataFrame(records)

        # Kite's 'date' column is a datetime object
        df["timestamp"] = pd.to_datetime(df["date"])
        df = df.drop(columns=["date"], errors="ignore")

        # Ensure UTC-aware timestamps for intraday, tz-naive for daily
        if df["timestamp"].dt.tz is None:
            # Kite returns IST-naive datetimes for intraday data;
            # localise to IST then convert to UTC for engine consistency
            try:
                df["timestamp"] = (
                    df["timestamp"]
                    .dt.tz_localize("Asia/Kolkata")
                    .dt.tz_convert("UTC")
                )
            except Exception:
                pass  # daily data stays tz-naive

        # Set index
        df = df.set_index("timestamp")
        df.index.name = "timestamp"

        # Ensure lowercase columns
        df.columns = [c.lower() for c in df.columns]

        # Keep only required columns
        for col in ["open", "high", "low", "close", "volume"]:
            if col not in df.columns:
                df[col] = 0

        df = df[["open", "high", "low", "close", "volume"]]

        # Sort chronologically
        df = df.sort_index()

        return df

    # ------------------------------------------------------------------
    # BaseDataSource interface
    # ------------------------------------------------------------------

    def load(self) -> pd.DataFrame:
        """Load default historical data (convenience method).

        Fetches ``default_days`` of history for ``default_symbol``
        at ``default_timeframe``.

        Returns:
            Engine-standard OHLCV DataFrame.
        """
        end = datetime.now()
        start = end - timedelta(days=self.default_days)
        return self.fetch_historical(
            symbol=self.default_symbol,
            timeframe=self.default_timeframe,
            start=start,
            end=end,
        )

    def fetch_historical(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data from Kite Connect.

        Handles Kite's per-request date-range limits by automatically
        chunking long date ranges.

        Args:
            symbol: Trading symbol (e.g. "RELIANCE", "RELIANCE.NS").
            timeframe: Bar timeframe (1m, 5m, 15m, 1h, 1D).
            start: Start datetime.
            end: End datetime.

        Returns:
            Engine-standard OHLCV DataFrame.
        """
        kite = self._get_kite()
        mapper = self._get_mapper()

        # Resolve instrument token
        instrument_token = mapper.get_instrument_token(symbol, self.exchange)
        kite_interval = self._kite_interval(timeframe)

        logger.info(
            f"Fetching {symbol} ({instrument_token}) "
            f"interval={kite_interval} from {start} to {end}"
        )

        # Kite limits: minute data = 60 days, day data = 2000 days, etc.
        # We chunk into safe windows to avoid API errors.
        max_days = self._max_days_per_request(timeframe)
        chunks = self._date_chunks(start, end, max_days)

        all_records = []
        for chunk_start, chunk_end in chunks:
            records = kite.historical_data(
                instrument_token=instrument_token,
                from_date=chunk_start,
                to_date=chunk_end,
                interval=kite_interval,
            )
            all_records.extend(records)
            logger.debug(
                f"  Chunk {chunk_start.date()} -> {chunk_end.date()}: "
                f"{len(records)} bars"
            )

        df = self._normalize_df(all_records)
        logger.info(f"Fetched {len(df)} total bars for {symbol}")
        return df

    def fetch_live(self, symbol: str) -> pd.Series:
        """Fetch latest quote for a symbol.

        Returns a pd.Series with open/high/low/close/volume from the
        most recent Kite quote.

        Note: For streaming live ticks, use KiteTicker (WebSocket)
        which is outside the scope of this data source.
        """
        kite = self._get_kite()
        mapper = self._get_mapper()
        instrument_token = mapper.get_instrument_token(symbol, self.exchange)

        # Kite quote key format: "EXCHANGE:TRADINGSYMBOL"
        base_sym = mapper.normalize_symbol_for_kite(symbol)
        quote_key = f"{self.exchange}:{base_sym}"
        quotes = kite.quote([quote_key])

        if quote_key not in quotes:
            raise ValueError(f"No quote returned for {quote_key}")

        q = quotes[quote_key]["ohlc"]
        return pd.Series(
            {
                "open": q["open"],
                "high": q["high"],
                "low": q["low"],
                "close": q["close"],
                "volume": quotes[quote_key].get("volume", 0),
            }
        )

    def list_instruments(self, exchange: Optional[str] = None) -> List[str]:
        """List all trading symbols available on an exchange.

        Args:
            exchange: Exchange name (default: ``self.exchange``).

        Returns:
            Sorted list of trading symbols.
        """
        kite = self._get_kite()
        exc = exchange or self.exchange
        instruments = kite.instruments(exc)
        symbols = sorted(set(inst["tradingsymbol"] for inst in instruments))
        logger.info(f"Found {len(symbols)} instruments on {exc}")
        return symbols

    def health_check(self) -> dict:
        """Check Kite API connectivity by calling kite.profile()."""
        try:
            from kiteconnect import KiteConnect  # noqa: F401
        except ImportError:
            return {
                "status": "error",
                "provider": "zerodha",
                "message": "kiteconnect package not installed",
            }

        creds_ok = bool(
            self.api_key and self.api_secret and self.access_token
        )
        if not creds_ok:
            return {
                "status": "error",
                "provider": "zerodha",
                "message": "Missing API credentials",
            }

        try:
            kite = self._get_kite()
            profile = kite.profile()
            return {
                "status": "ok",
                "provider": "zerodha",
                "message": f"Connected as {profile.get('user_name', 'unknown')}",
                "user_id": profile.get("user_id"),
            }
        except Exception as exc:
            return {
                "status": "error",
                "provider": "zerodha",
                "message": f"Connection failed: {exc}",
            }

    # ------------------------------------------------------------------
    # Chunking helpers (Kite rate / date-range limits)
    # ------------------------------------------------------------------

    @staticmethod
    def _max_days_per_request(timeframe: Timeframe) -> int:
        """Maximum calendar-day span Kite allows per historical request."""
        if timeframe == Timeframe.MINUTE_1:
            return 60
        elif timeframe in (Timeframe.MINUTE_5, Timeframe.MINUTE_15):
            return 100
        elif timeframe == Timeframe.HOURLY:
            return 400
        else:  # daily
            return 2000

    @staticmethod
    def _date_chunks(
        start: datetime,
        end: datetime,
        max_days: int,
    ) -> list[tuple[datetime, datetime]]:
        """Split a date range into Kite-safe chunks."""
        chunks = []
        current = start
        while current < end:
            chunk_end = min(current + timedelta(days=max_days), end)
            chunks.append((current, chunk_end))
            current = chunk_end + timedelta(seconds=1)
        return chunks


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
