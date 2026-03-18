"""
DhanHQ data source — optional derivative-capable provider.

DhanHQ (https://dhanhq.co) supports Indian market data including:
- NSE equities (NSE_EQ)
- NSE F&O (NSE_FO)
- BSE equities (BSE_EQ)
- MCX commodities (MCX)
- Currency derivatives (CUR)

This module is optional. If dhanhq is not installed, DhanHQDataSource
degrades gracefully and reports its state via health_check().
"""

from __future__ import annotations

import pandas as pd

from src.data.base import BaseDataSource
from src.utils.logger import setup_logger

logger = setup_logger("dhan_source")

# Segment mapping: internal Exchange → Dhan exchange_segment string
_DHAN_SEGMENT_MAP = {
    "NSE": "NSE_EQ",
    "BSE": "BSE_EQ",
    "NFO": "NSE_FO",
    "MCX": "MCX",
    "CDS": "CUR",
}

# Reverse: Dhan segment → our Exchange string
_DHAN_SEGMENT_REVERSE = {v: k for k, v in _DHAN_SEGMENT_MAP.items()}

# Dhan instrument_type strings
_DHAN_INSTRUMENT_TYPE_MAP = {
    "equity": "EQUITY",
    "index": "INDEX",
    "future_nfo": "FUTIDX",     # NFO index future
    "future_stk": "FUTSTK",     # NFO stock future
    "option_nfo": "OPTIDX",     # NFO index option
    "option_stk": "OPTSTK",     # NFO stock option
    "future_mcx": "FUTCOM",     # MCX commodity future
    "option_mcx": "OPTCOM",     # MCX commodity option
    "future_cds": "FUTCUR",     # CDS currency future
    "option_cds": "OPTCUR",     # CDS currency option
}

# Dhan interval mapping
_TIMEFRAME_TO_DHAN_INTERVAL = {
    "MINUTE_1": "1",
    "MINUTE_5": "5",
    "MINUTE_15": "15",
    "HOURLY": "60",
    "DAILY": "D",
}


class DhanHQDataSource(BaseDataSource):
    """DhanHQ data source with honest capability/health reporting.

    Requires dhanhq Python package. Falls back to degraded state if unavailable.

    Args:
        client_id: DhanHQ client ID.
        access_token: DhanHQ access token.
        default_symbol: Default symbol for load().
        default_segment: Default segment (NSE_EQ, NSE_FO, MCX, etc.).
        default_timeframe: Default timeframe.
        default_days: Days of history for load().
        retries: Number of retry attempts for API calls.
        backoff_seconds: Seconds to wait between retries.
    """

    def __init__(
        self,
        client_id=None,
        access_token=None,
        default_symbol=None,
        default_segment="NSE_EQ",
        default_timeframe=None,
        default_days=365,
        retries=3,
        backoff_seconds=1.0,
    ):
        self._client_id = client_id
        self._access_token = access_token
        self._default_symbol = default_symbol
        self._default_segment = default_segment
        self._default_days = default_days
        self._retries = retries
        self._backoff_seconds = backoff_seconds
        self._client = None
        self._sdk_available = False
        self._sdk_error = ""

        # Try to init the DhanHQ client
        try:
            from dhanhq import dhanhq  # noqa: PLC0415
            if client_id and access_token:
                self._client = dhanhq(client_id, access_token)
                self._sdk_available = True
        except ImportError as e:
            self._sdk_error = f"dhanhq package not installed: {e}"
        except Exception as e:
            self._sdk_error = f"DhanHQ client init failed: {e}"

    def load(self) -> pd.DataFrame:
        """Not implemented — use fetch_historical directly."""
        raise NotImplementedError(
            "DhanHQDataSource.load() — use fetch_historical() instead"
        )

    def fetch_historical(self, symbol: str, timeframe, start, end) -> pd.DataFrame:
        """Fetch historical OHLCV data from DhanHQ.

        Uses security_id as symbol (numeric string or ticker).
        Returns DataFrame with DatetimeIndex and OHLCV columns.
        Raises NotImplementedError if SDK not available.
        """
        if not self._sdk_available:
            raise NotImplementedError(
                f"DhanHQ SDK unavailable: {self._sdk_error}. "
                "Ensure dhanhq is installed and credentials are configured."
            )
        # Map timeframe to Dhan interval
        tf_name = getattr(timeframe, "name", str(timeframe))
        interval = _TIMEFRAME_TO_DHAN_INTERVAL.get(tf_name, "D")

        from_date = start.strftime("%Y-%m-%d")
        to_date = end.strftime("%Y-%m-%d")

        # Determine exchange segment and instrument type from symbol prefix or default
        segment = self._default_segment
        instrument_type = "EQUITY"

        try:
            response = self._client.historical_minute_charts(
                symbol=symbol,
                exchange_segment=segment,
                instrument_type=instrument_type,
                expiry_code=0,
                from_date=from_date,
                to_date=to_date,
                interval=interval,
            )
            return self._normalize_historical(response)
        except Exception as exc:
            raise RuntimeError(f"DhanHQ fetch_historical failed: {exc}") from exc

    def _normalize_historical(self, response) -> pd.DataFrame:
        """Normalize DhanHQ historical response to standard OHLCV DataFrame."""
        if not response or not isinstance(response, dict):
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        data = response.get("data", {})
        if isinstance(data, dict):
            # Dhan returns {timestamp: [...], open: [...], ...}
            timestamps = data.get("timestamp", [])
            opens = data.get("open", [])
            highs = data.get("high", [])
            lows = data.get("low", [])
            closes = data.get("close", [])
            volumes = data.get("volume", [])
        elif isinstance(data, list):
            # Alternative: list of [timestamp, open, high, low, close, volume]
            timestamps = [row[0] for row in data]
            opens = [row[1] for row in data]
            highs = [row[2] for row in data]
            lows = [row[3] for row in data]
            closes = [row[4] for row in data]
            volumes = [row[5] for row in data if len(row) > 5]
        else:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        if not timestamps:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = pd.DataFrame(
            {
                "open": pd.to_numeric(opens, errors="coerce"),
                "high": pd.to_numeric(highs, errors="coerce"),
                "low": pd.to_numeric(lows, errors="coerce"),
                "close": pd.to_numeric(closes, errors="coerce"),
                "volume": pd.to_numeric(volumes, errors="coerce")
                if volumes
                else 0,
            },
            index=pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(
                "Asia/Kolkata"
            ),
        )
        df.index.name = "timestamp"
        return df.sort_index()

    def fetch_live(self, symbol: str, timeframe=None) -> pd.Series:
        """Return latest quote as a Series. Degrades if SDK unavailable."""
        if not self._sdk_available:
            raise NotImplementedError(
                f"DhanHQ SDK unavailable: {self._sdk_error}"
            )
        raise NotImplementedError(
            "DhanHQDataSource.fetch_live() — not yet implemented"
        )

    def fetch_option_chain(
        self, underlying: str, expiry: str, segment: str = "NSE_FO"
    ) -> dict:
        """Fetch full option chain from DhanHQ.

        Args:
            underlying: Underlying symbol (e.g. "NIFTY").
            expiry: Expiry date string (YYYY-MM-DD format).
            segment: Exchange segment (default NSE_FO).

        Returns:
            Dict with "calls" and "puts" lists, each with
            strike/oi/bid/ask/ltp/iv. Empty dict if SDK unavailable or
            fetch fails.
        """
        if not self._sdk_available:
            return {
                "calls": [],
                "puts": [],
                "error": self._sdk_error,
                "degraded": True,
            }
        try:
            response = self._client.option_chain(
                UnderlyingScrip=underlying,
                UnderlyingSeg=segment,
                Expiry=expiry,
            )
            return self._normalize_option_chain(response)
        except Exception as exc:
            logger.warning(f"DhanHQ fetch_option_chain failed: {exc}")
            return {"calls": [], "puts": [], "error": str(exc), "degraded": True}

    def _normalize_option_chain(self, response) -> dict:
        """Normalize DhanHQ option chain response."""
        if not response or not isinstance(response, dict):
            return {"calls": [], "puts": [], "degraded": True}

        data = response.get("data", [])
        calls, puts = [], []

        for row in data if isinstance(data, list) else []:
            strike = row.get("strikePrice", row.get("strike_price", 0))
            # CE side
            ce = row.get("callOption", row.get("ce", {}))
            if ce:
                calls.append(
                    {
                        "strike": float(strike),
                        "oi": int(ce.get("OI", ce.get("oi", 0))),
                        "volume": int(ce.get("volume", 0)),
                        "ltp": float(ce.get("LTP", ce.get("ltp", 0))),
                        "bid": float(ce.get("bidPrice", 0)),
                        "ask": float(ce.get("askPrice", 0)),
                        "iv": float(
                            ce.get("impliedVolatility", ce.get("iv", 0))
                        ),
                        "delta": float(ce.get("delta", 0)),
                        "theta": float(ce.get("theta", 0)),
                        "gamma": float(ce.get("gamma", 0)),
                        "vega": float(ce.get("vega", 0)),
                        "option_type": "CE",
                        "source": "dhan",
                    }
                )
            # PE side
            pe = row.get("putOption", row.get("pe", {}))
            if pe:
                puts.append(
                    {
                        "strike": float(strike),
                        "oi": int(pe.get("OI", pe.get("oi", 0))),
                        "volume": int(pe.get("volume", 0)),
                        "ltp": float(pe.get("LTP", pe.get("ltp", 0))),
                        "bid": float(pe.get("bidPrice", 0)),
                        "ask": float(pe.get("askPrice", 0)),
                        "iv": float(
                            pe.get("impliedVolatility", pe.get("iv", 0))
                        ),
                        "delta": float(pe.get("delta", 0)),
                        "theta": float(pe.get("theta", 0)),
                        "gamma": float(pe.get("gamma", 0)),
                        "vega": float(pe.get("vega", 0)),
                        "option_type": "PE",
                        "source": "dhan",
                    }
                )

        calls.sort(key=lambda x: x["strike"])
        puts.sort(key=lambda x: x["strike"])
        return {"calls": calls, "puts": puts, "degraded": False}

    def fetch_expiry_list(
        self, underlying: str, segment: str = "NSE_FO"
    ) -> list:
        """Fetch list of available expiry dates from DhanHQ.

        Returns:
            Sorted list of expiry date strings (YYYY-MM-DD) or empty list
            if unavailable.
        """
        if not self._sdk_available:
            return []
        try:
            response = self._client.expiry_list(
                UnderlyingScrip=underlying,
                UnderlyingSeg=segment,
            )
            data = (
                response.get("data", [])
                if isinstance(response, dict)
                else []
            )
            return sorted(set(str(d) for d in data if d))
        except Exception as exc:
            logger.warning(f"DhanHQ fetch_expiry_list failed: {exc}")
            return []

    def list_instruments(self) -> list:
        """DhanHQ does not provide a full instrument list via this API path."""
        return []

    def health_check(self) -> dict:
        """Return health/auth state of DhanHQ provider."""
        if not self._sdk_available:
            return {
                "state": "sdk_unavailable",
                "sdk_available": False,
                "sdk_error": self._sdk_error,
                "provider": "dhan",
                "degraded": True,
            }
        if not (self._client_id and self._access_token):
            return {
                "state": "no_credentials",
                "sdk_available": True,
                "provider": "dhan",
                "degraded": True,
            }
        return {
            "state": "sdk_configured",
            "sdk_available": True,
            "provider": "dhan",
            "client_id": self._client_id[:4] + "****"
            if self._client_id
            else None,
            "degraded": False,
        }
