"""
Broker API data source implementations for Indian markets.

- ZerodhaDataSource: historical + quote snapshots with retry/degraded status.
- UpstoxDataSource: safe data provider with honest capability/health reporting,
  including optional CSV fallback when SDK/integration is unavailable.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, List, Optional

import pandas as pd

from src.data.base import BaseDataSource, Timeframe
from src.data.symbol_mapping import SymbolMapper
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

_TIMEFRAME_TO_UPSTOX_SUFFIX = {
    Timeframe.MINUTE_1: "1M",
    Timeframe.MINUTE_5: "5M",
    Timeframe.MINUTE_15: "15M",
    Timeframe.HOURLY: "1H",
    Timeframe.DAILY: "1D",
}


def _is_transient_error(exc: Exception) -> bool:
    text = str(exc).lower()
    transient_tokens = (
        "timeout",
        "temporarily",
        "connection reset",
        "connection aborted",
        "connection refused",
        "rate limit",
        "429",
        "503",
        "gateway",
        "network",
    )
    return any(token in text for token in transient_tokens)


def _call_with_retries(
    func: Callable[[], Any],
    *,
    retries: int,
    backoff_seconds: float,
) -> Any:
    attempt = 0
    while True:
        attempt += 1
        try:
            return func()
        except Exception as exc:
            if attempt > retries or not _is_transient_error(exc):
                raise
            time.sleep(max(0.0, float(backoff_seconds)) * attempt)


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
        request_retries: int = 2,
        retry_backoff_seconds: float = 0.4,
        live_stale_threshold_seconds: int = 120,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.default_symbol = default_symbol
        self.default_timeframe = default_timeframe
        self.default_days = default_days
        self.exchange = exchange
        self.request_retries = max(0, int(request_retries))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self.live_stale_threshold_seconds = max(1, int(live_stale_threshold_seconds))

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
            records = _call_with_retries(
                lambda cs=chunk_start, ce=chunk_end: kite.historical_data(
                    instrument_token=instrument_token,
                    from_date=cs,
                    to_date=ce,
                    interval=kite_interval,
                ),
                retries=self.request_retries,
                backoff_seconds=self.retry_backoff_seconds,
            )
            all_records.extend(records)
            logger.debug(
                f"  Chunk {chunk_start.date()} -> {chunk_end.date()}: "
                f"{len(records)} bars"
            )

        df = self._normalize_df(all_records)
        df.attrs["data_quality"] = {
            "schema_version": "v1",
            "provider": "zerodha",
            "source": "kite_historical_data",
            "generated_at": datetime.now(UTC).isoformat(),
            "fallback_provider": None,
            "partial_data": False,
            "stale_data": False,
            "missing_bars_count": 0,
            "auth_degraded": False,
            "retry_attempts": self.request_retries,
        }
        logger.info(f"Fetched {len(df)} total bars for {symbol}")
        return df

    def fetch_live(
        self,
        symbol: str,
        timeframe: Timeframe | str | None = None,
    ) -> pd.Series:
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
        quotes = _call_with_retries(
            lambda: kite.quote([quote_key]),
            retries=self.request_retries,
            backoff_seconds=self.retry_backoff_seconds,
        )

        if quote_key not in quotes:
            raise ValueError(f"No quote returned for {quote_key}")

        q = quotes[quote_key]["ohlc"]
        series = pd.Series(
            {
                "open": q["open"],
                "high": q["high"],
                "low": q["low"],
                "close": q["close"],
                "volume": quotes[quote_key].get("volume", 0),
            }
        )
        fetched_at = pd.Timestamp.now(tz="UTC")
        quote_ts = quotes[quote_key].get("timestamp") or quotes[quote_key].get("last_trade_time")
        quote_timestamp = pd.Timestamp(quote_ts) if quote_ts is not None else fetched_at
        freshness_seconds = max(0.0, (fetched_at - quote_timestamp).total_seconds())
        series.attrs["data_quality"] = {
            "schema_version": "v1",
            "provider": "zerodha",
            "source": "kite_quote",
            "generated_at": fetched_at.isoformat(),
            "symbol": symbol,
            "timeframe": str(timeframe.value if isinstance(timeframe, Timeframe) else timeframe or ""),
            "freshness_seconds": freshness_seconds,
            "stale_data": freshness_seconds > float(self.live_stale_threshold_seconds),
            "fallback_provider": None,
            "partial_data": False,
            "missing_bars_count": 0,
            "auth_degraded": False,
        }
        return series

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
                "state": "package_missing",
                "message": "kiteconnect package not installed",
                "implementation_status": "partial",
                "supports_historical_data": True,
                "supports_live_quotes": True,
                "auth_degraded": True,
            }

        creds_ok = bool(
            self.api_key and self.api_secret and self.access_token
        )
        if not creds_ok:
            return {
                "status": "degraded",
                "provider": "zerodha",
                "state": "credentials_missing",
                "message": "Missing API credentials",
                "implementation_status": "partial",
                "supports_historical_data": True,
                "supports_live_quotes": True,
                "auth_degraded": True,
            }

        try:
            kite = self._get_kite()
            profile = kite.profile()
            return {
                "status": "ok",
                "provider": "zerodha",
                "state": "authenticated",
                "message": f"Connected as {profile.get('user_name', 'unknown')}",
                "user_id": profile.get("user_id"),
                "implementation_status": "partial",
                "supports_historical_data": True,
                "supports_live_quotes": True,
                "auth_degraded": False,
            }
        except Exception as exc:
            text = str(exc).lower()
            state = "auth_invalid"
            if "token" in text and ("expired" in text or "invalid" in text):
                state = "token_invalid_or_expired"
            elif _is_transient_error(exc):
                state = "transient_connectivity_error"
            return {
                "status": "degraded",
                "provider": "zerodha",
                "state": state,
                "message": f"Connection failed: {exc}",
                "implementation_status": "partial",
                "supports_historical_data": True,
                "supports_live_quotes": True,
                "auth_degraded": True,
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
    """Upstox data source with safe fallback behavior.

    Current implementation priority:
    1) Optional SDK path when the package and credentials are available.
    2) Deterministic CSV fallback for historical/latest-bar workflows.

    This class does not place or route orders.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        access_token: str,
        default_symbol: str = "RELIANCE",
        default_timeframe: Timeframe = Timeframe.DAILY,
        default_days: int = 365,
        data_dir: str = "data",
        request_retries: int = 2,
        retry_backoff_seconds: float = 0.4,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.default_symbol = default_symbol
        self.default_timeframe = default_timeframe
        self.default_days = int(default_days)
        self.data_dir = Path(data_dir)
        self.request_retries = max(0, int(request_retries))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self._symbol_mapper = SymbolMapper()

    def load(self) -> pd.DataFrame:
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
        # CSV fallback path (works without SDK/credentials and keeps workflows usable).
        fallback_df = self._load_from_csv_fallback(symbol, timeframe, start, end)
        if fallback_df is not None:
            return fallback_df

        # SDK path remains optional and explicit.
        raise NotImplementedError(
            "Upstox historical API path is not available in this environment. "
            "Enable upstox SDK + credentials, or provide CSV fallback data in "
            f"{self.data_dir} as <SYMBOL>_<TF>.csv."
        )

    def fetch_live(
        self,
        symbol: str,
        timeframe: Timeframe | str | None = None,
    ) -> dict[str, Any]:
        tf = timeframe if isinstance(timeframe, Timeframe) else self._normalize_timeframe(timeframe)
        # Safe fallback: latest bar from local CSV data.
        end = datetime.now()
        start = end - timedelta(days=max(self.default_days, 3650))
        frame = self._load_from_csv_fallback(symbol, tf, start, end)
        if frame is None or frame.empty:
            raise NotImplementedError(
                "Upstox live quote path unavailable and CSV fallback has no data. "
                "Use provider='indian_csv' for deterministic local workflows."
            )

        last = frame.iloc[-1]
        timestamp = pd.Timestamp(frame.index[-1])
        ts_utc = timestamp.tz_localize("Asia/Kolkata").tz_convert("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
        freshness_seconds = max(0.0, (pd.Timestamp.now(tz="UTC") - ts_utc).total_seconds())
        quality = {
            "schema_version": "v1",
            "provider": "upstox",
            "source": "csv_fallback_latest_bar",
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "fallback_provider": "csv",
            "freshness_seconds": freshness_seconds,
            "stale_data": freshness_seconds > 120.0,
            "partial_data": False,
            "auth_degraded": not self._credentials_configured(),
            "missing_bars_count": 0,
        }
        return {
            "symbol": self._symbol_mapper.to_canonical(symbol),
            "timeframe": tf.value,
            "timestamp": timestamp.isoformat(),
            "close": float(last["close"]),
            "bars": int(len(frame)),
            "data_quality": quality,
        }

    def list_instruments(self) -> List[str]:
        symbols: set[str] = set()
        if self.data_dir.exists():
            for candidate in self.data_dir.glob("*_1D.csv"):
                symbols.add(self._symbol_mapper.to_canonical(self._symbol_mapper.from_filename(candidate.name)))
        return sorted(symbols)

    def health_check(self) -> dict:
        """Check Upstox readiness with explicit degraded-state reporting."""
        has_sdk = self._has_sdk()
        creds_ok = self._credentials_configured()
        fallback_ready = self._csv_fallback_available()

        if has_sdk and creds_ok:
            return {
                "status": "degraded",
                "provider": "upstox",
                "state": "sdk_present_auth_configured",
                "message": "Upstox SDK credentials are configured; API path is not wired yet.",
                "implementation_status": "partial",
                "supports_historical_data": True,
                "supports_live_quotes": False,
                "fallback_available": fallback_ready,
                "auth_degraded": False,
            }
        if fallback_ready:
            return {
                "status": "degraded",
                "provider": "upstox",
                "state": "csv_fallback_only",
                "message": "Upstox API unavailable; CSV fallback is active for safe data workflows.",
                "implementation_status": "partial",
                "supports_historical_data": True,
                "supports_live_quotes": True,
                "fallback_available": True,
                "auth_degraded": True,
            }
        return {
            "status": "not_implemented",
            "provider": "upstox",
            "state": "sdk_and_fallback_unavailable",
            "message": (
                "Upstox data path is not available. Install SDK+credentials or "
                f"provide CSV data under {self.data_dir}."
            ),
            "implementation_status": "partial",
            "supports_historical_data": False,
            "supports_live_quotes": False,
            "fallback_available": False,
            "auth_degraded": True,
        }

    def _csv_fallback_path(self, symbol: str, timeframe: Timeframe) -> Path:
        stem = self._symbol_mapper.normalize(symbol)
        suffix = _TIMEFRAME_TO_UPSTOX_SUFFIX.get(timeframe, "1D")
        return self.data_dir / f"{stem}_{suffix}.csv"

    def _load_from_csv_fallback(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> Optional[pd.DataFrame]:
        path = self._csv_fallback_path(symbol, timeframe)
        if not path.exists():
            return None

        frame = pd.read_csv(path)
        if "timestamp" not in frame.columns:
            raise ValueError(f"CSV fallback file missing 'timestamp' column: {path}")

        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        frame = frame.set_index("timestamp").sort_index()
        frame.columns = [str(col).strip().lower() for col in frame.columns]
        for column in ("open", "high", "low", "close", "volume"):
            if column not in frame.columns:
                frame[column] = 0.0
        frame = frame[["open", "high", "low", "close", "volume"]]
        frame = frame.loc[(frame.index >= pd.Timestamp(start)) & (frame.index <= pd.Timestamp(end))]
        frame.attrs["data_quality"] = {
            "schema_version": "v1",
            "provider": "upstox",
            "source": "csv_fallback",
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "fallback_provider": "csv",
            "stale_data": False,
            "partial_data": False,
            "missing_bars_count": 0,
            "auth_degraded": not self._credentials_configured(),
        }
        return frame

    @staticmethod
    def _normalize_timeframe(timeframe: Timeframe | str | None) -> Timeframe:
        if timeframe is None:
            return Timeframe.DAILY
        if isinstance(timeframe, Timeframe):
            return timeframe
        key = str(timeframe).strip().lower()
        mapping = {
            "1m": Timeframe.MINUTE_1,
            "5m": Timeframe.MINUTE_5,
            "15m": Timeframe.MINUTE_15,
            "1h": Timeframe.HOURLY,
            "60m": Timeframe.HOURLY,
            "1d": Timeframe.DAILY,
            "day": Timeframe.DAILY,
            "daily": Timeframe.DAILY,
        }
        if key not in mapping:
            raise ValueError(f"Unsupported timeframe for UpstoxDataSource: {timeframe}")
        return mapping[key]

    def _has_sdk(self) -> bool:
        try:
            import upstox_client  # noqa: F401
            return True
        except ImportError:
            return False

    def _credentials_configured(self) -> bool:
        return bool(self.api_key and self.api_secret and self.access_token)

    def _csv_fallback_available(self) -> bool:
        if not self.data_dir.exists():
            return False
        return any(self.data_dir.glob("*_1D.csv"))
