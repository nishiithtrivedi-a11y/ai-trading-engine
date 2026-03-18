"""
Normalized quote model with data quality flags.

NormalizedQuote is the canonical quote object in the system — a provider-agnostic
representation of market data with explicit quality metadata.

Supported normalization sources:
- Kite (Zerodha) quote dict  -> normalize_kite_quote()
- Kite historical OHLCV row  -> normalize_kite_ohlc_row()
- Upstox quote dict          -> normalize_upstox_quote() (best-effort)
- Pandas Series              -> quote_from_series()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd


@dataclass
class DataQualityFlags:
    """Quality and completeness flags for a NormalizedQuote."""

    is_stale: bool = False
    """True if the quote timestamp is significantly behind expected refresh time."""

    has_oi: bool = False
    """True if open interest data is present and non-zero."""

    has_depth: bool = False
    """True if market depth (bid/ask ladder) data is available."""

    has_partial_metadata: bool = False
    """True if some metadata fields are missing or approximate."""

    unsupported_segment: bool = False
    """True if the quote comes from a segment not fully supported by the provider."""

    degraded_auth: bool = False
    """True if the quote was obtained with degraded/fallback authentication."""

    missing_volume: bool = False
    """True if volume data is absent or zero when it should be present."""

    notes: list[str] = field(default_factory=list)
    """Human-readable quality notes for debugging."""


@dataclass
class NormalizedQuote:
    """Provider-agnostic normalized quote.

    All price/volume fields are Optional — downstream consumers must
    handle None values explicitly.
    """

    symbol: str
    """Canonical symbol string (e.g. "NSE:RELIANCE-EQ")."""

    provider: str
    """Provider identifier (e.g. "zerodha", "upstox")."""

    timestamp: Optional[datetime]
    """Quote timestamp in UTC or local time (provider-dependent)."""

    last_price: Optional[float]
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    volume: Optional[int]
    oi: Optional[int]
    """Open interest — relevant for futures and options."""

    bid: Optional[float]
    ask: Optional[float]
    depth_bid_qty: Optional[int]
    depth_ask_qty: Optional[int]

    quality: DataQualityFlags = field(default_factory=DataQualityFlags)
    raw: dict = field(default_factory=dict)
    """Original provider payload for debugging."""

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_complete(self) -> bool:
        """True if all OHLCV fields are present (not None)."""
        return all(
            v is not None
            for v in [self.open, self.high, self.low, self.close, self.volume]
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise to a plain dict (suitable for JSON / DataFrame row)."""
        return {
            "symbol": self.symbol,
            "provider": self.provider,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "last_price": self.last_price,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "oi": self.oi,
            "bid": self.bid,
            "ask": self.ask,
            "depth_bid_qty": self.depth_bid_qty,
            "depth_ask_qty": self.depth_ask_qty,
            "quality": {
                "is_stale": self.quality.is_stale,
                "has_oi": self.quality.has_oi,
                "has_depth": self.quality.has_depth,
                "has_partial_metadata": self.quality.has_partial_metadata,
                "unsupported_segment": self.quality.unsupported_segment,
                "degraded_auth": self.quality.degraded_auth,
                "missing_volume": self.quality.missing_volume,
                "notes": list(self.quality.notes),
            },
        }


# ---------------------------------------------------------------------------
# Kite quote normalizer
# ---------------------------------------------------------------------------

def normalize_kite_quote(canonical: str, kite_quote: dict) -> NormalizedQuote:
    """Normalize a Kite quote dict to NormalizedQuote.

    Kite quote keys:
        last_price (float)
        ohlc (dict with open/high/low/close)
        volume (int)
        oi (int) — open interest, may be absent for equities
        depth (dict with buy/sell lists)

    Parameters
    ----------
    canonical:
        Canonical symbol string for this quote.
    kite_quote:
        Raw dict returned by kite.quote() for a single instrument.

    Returns
    -------
    NormalizedQuote
    """
    flags = DataQualityFlags()

    last_price = _safe_float(kite_quote.get("last_price"))
    ohlc = kite_quote.get("ohlc") or {}
    open_ = _safe_float(ohlc.get("open"))
    high = _safe_float(ohlc.get("high"))
    low = _safe_float(ohlc.get("low"))
    close = _safe_float(ohlc.get("close"))
    volume = _safe_int(kite_quote.get("volume"))

    # OI
    oi_raw = kite_quote.get("oi")
    oi = _safe_int(oi_raw)
    flags.has_oi = oi is not None and oi > 0

    # Market depth
    depth = kite_quote.get("depth") or {}
    buy_orders = depth.get("buy") or []
    sell_orders = depth.get("sell") or []

    bid: Optional[float] = None
    ask: Optional[float] = None
    depth_bid_qty: Optional[int] = None
    depth_ask_qty: Optional[int] = None

    if buy_orders:
        best_bid = buy_orders[0]
        bid = _safe_float(best_bid.get("price"))
        depth_bid_qty = _safe_int(best_bid.get("quantity"))
        flags.has_depth = True
    if sell_orders:
        best_ask = sell_orders[0]
        ask = _safe_float(best_ask.get("price"))
        depth_ask_qty = _safe_int(best_ask.get("quantity"))
        flags.has_depth = True

    if not flags.has_depth:
        flags.notes.append("No market depth data in quote")

    if volume is None or volume == 0:
        flags.missing_volume = True

    # Timestamp
    ts_raw = kite_quote.get("timestamp") or kite_quote.get("last_trade_time")
    timestamp = _parse_timestamp(ts_raw)

    return NormalizedQuote(
        symbol=canonical,
        provider="zerodha",
        timestamp=timestamp,
        last_price=last_price,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        oi=oi,
        bid=bid,
        ask=ask,
        depth_bid_qty=depth_bid_qty,
        depth_ask_qty=depth_ask_qty,
        quality=flags,
        raw=dict(kite_quote),
    )


# ---------------------------------------------------------------------------
# Kite OHLC row normalizer (historical data)
# ---------------------------------------------------------------------------

def normalize_kite_ohlc_row(canonical: str, row: dict) -> NormalizedQuote:
    """Normalize a single row from Kite historical data.

    Historical data row keys: date, open, high, low, close, volume
    (OI available in derivative historical data as 'oi').

    Parameters
    ----------
    canonical:
        Canonical symbol string.
    row:
        Single row dict from Kite historical data.

    Returns
    -------
    NormalizedQuote
    """
    flags = DataQualityFlags()

    open_ = _safe_float(row.get("open"))
    high = _safe_float(row.get("high"))
    low = _safe_float(row.get("low"))
    close = _safe_float(row.get("close"))
    volume = _safe_int(row.get("volume"))
    oi = _safe_int(row.get("oi"))

    flags.has_oi = oi is not None and oi > 0
    if volume is None or volume == 0:
        flags.missing_volume = True

    ts_raw = row.get("date")
    timestamp = _parse_timestamp(ts_raw)

    return NormalizedQuote(
        symbol=canonical,
        provider="zerodha",
        timestamp=timestamp,
        last_price=close,  # Use close as last_price for historical rows
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        oi=oi,
        bid=None,
        ask=None,
        depth_bid_qty=None,
        depth_ask_qty=None,
        quality=flags,
        raw=dict(row),
    )


# ---------------------------------------------------------------------------
# Upstox quote normalizer (best-effort)
# ---------------------------------------------------------------------------

def normalize_upstox_quote(canonical: str, upstox_quote: dict) -> NormalizedQuote:
    """Normalize an Upstox quote payload (best-effort).

    Upstox SDK is not fully implemented; this normalizer maps known field names.
    Quality flags are set conservatively.

    Parameters
    ----------
    canonical:
        Canonical symbol string.
    upstox_quote:
        Raw Upstox quote dict.

    Returns
    -------
    NormalizedQuote
    """
    flags = DataQualityFlags()
    flags.has_partial_metadata = True
    flags.notes.append("Upstox SDK integration is best-effort; fields may vary")

    last_price = (
        _safe_float(upstox_quote.get("last_price"))
        or _safe_float(upstox_quote.get("ltp"))
    )
    open_ = _safe_float(upstox_quote.get("open"))
    high = _safe_float(upstox_quote.get("high"))
    low = _safe_float(upstox_quote.get("low"))
    close = _safe_float(upstox_quote.get("close")) or _safe_float(upstox_quote.get("prev_close"))
    volume = _safe_int(upstox_quote.get("volume"))
    oi = _safe_int(upstox_quote.get("oi")) or _safe_int(upstox_quote.get("open_interest"))

    flags.has_oi = oi is not None and oi > 0
    if volume is None or volume == 0:
        flags.missing_volume = True

    ts_raw = upstox_quote.get("timestamp") or upstox_quote.get("exchange_timestamp")
    timestamp = _parse_timestamp(ts_raw)

    return NormalizedQuote(
        symbol=canonical,
        provider="upstox",
        timestamp=timestamp,
        last_price=last_price,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        oi=oi,
        bid=None,
        ask=None,
        depth_bid_qty=None,
        depth_ask_qty=None,
        quality=flags,
        raw=dict(upstox_quote),
    )


# ---------------------------------------------------------------------------
# Pandas Series normalizer
# ---------------------------------------------------------------------------

def quote_from_series(
    canonical: str,
    series: pd.Series,
    provider: str = "unknown",
) -> NormalizedQuote:
    """Create a NormalizedQuote from a pandas Series (e.g. latest OHLCV bar).

    Expected index labels: open, high, low, close, volume
    Optional: oi, timestamp, last_price

    Parameters
    ----------
    canonical:
        Canonical symbol string.
    series:
        Pandas Series with OHLCV data.
    provider:
        Provider name string.

    Returns
    -------
    NormalizedQuote
    """
    flags = DataQualityFlags()

    def _get(key: str):
        for k in (key, key.lower(), key.upper()):
            if k in series.index:
                return series[k]
        return None

    open_ = _safe_float(_get("open"))
    high = _safe_float(_get("high"))
    low = _safe_float(_get("low"))
    close = _safe_float(_get("close"))
    volume = _safe_int(_get("volume"))
    oi = _safe_int(_get("oi"))
    last_price = _safe_float(_get("last_price")) or close

    flags.has_oi = oi is not None and oi > 0
    if volume is None or volume == 0:
        flags.missing_volume = True

    ts_raw = _get("timestamp") or _get("date") or _get("time")
    timestamp = _parse_timestamp(ts_raw)

    return NormalizedQuote(
        symbol=canonical,
        provider=provider,
        timestamp=timestamp,
        last_price=last_price,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        oi=oi,
        bid=None,
        ask=None,
        depth_bid_qty=None,
        depth_ask_qty=None,
        quality=flags,
        raw={},
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else f  # NaN check
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> Optional[int]:
    if val is None:
        return None
    try:
        f = float(val)
        if f != f:  # NaN
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


def _parse_timestamp(raw) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw or raw.lower() in ("", "nan", "nat", "none", "null"):
            return None
        try:
            return datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            return None
    # pandas Timestamp
    try:
        return raw.to_pydatetime()
    except AttributeError:
        pass
    return None
