from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Optional

import pandas as pd


DEFAULT_TIMEZONE = "Asia/Kolkata"


@dataclass(frozen=True)
class MarketSessionConfig:
    market_open: time = time(9, 15)
    market_close: time = time(15, 30)
    timezone: str = DEFAULT_TIMEZONE


class MarketSessionError(Exception):
    """Raised when market session utilities receive invalid input."""


def ensure_timestamp(timestamp: pd.Timestamp | str) -> pd.Timestamp:
    """Convert input to pandas Timestamp."""
    if isinstance(timestamp, pd.Timestamp):
        return timestamp
    try:
        return pd.Timestamp(timestamp)
    except Exception as exc:
        raise MarketSessionError(f"Invalid timestamp: {timestamp}") from exc


def localize_or_convert_timestamp(
    timestamp: pd.Timestamp | str,
    timezone: str = DEFAULT_TIMEZONE,
) -> pd.Timestamp:
    """
    Ensure timestamp is timezone-aware in the given timezone.

    - If naive, assume it already belongs to the given timezone and localize it.
    - If tz-aware, convert it to the given timezone.
    """
    ts = ensure_timestamp(timestamp)

    if ts.tzinfo is None:
        return ts.tz_localize(timezone)

    return ts.tz_convert(timezone)


def get_session_date(
    timestamp: pd.Timestamp | str,
    timezone: str = DEFAULT_TIMEZONE,
) -> pd.Timestamp:
    """Return normalized session date in local timezone."""
    ts = localize_or_convert_timestamp(timestamp, timezone=timezone)
    return ts.normalize()


def is_market_open(
    timestamp: pd.Timestamp | str,
    config: Optional[MarketSessionConfig] = None,
) -> bool:
    """Check whether timestamp falls inside NSE cash market hours."""
    cfg = config or MarketSessionConfig()
    ts = localize_or_convert_timestamp(timestamp, timezone=cfg.timezone)
    current_t = ts.time()
    return cfg.market_open <= current_t <= cfg.market_close


def is_session_start(
    timestamp: pd.Timestamp | str,
    config: Optional[MarketSessionConfig] = None,
) -> bool:
    """True only for the bar stamped exactly at market open."""
    cfg = config or MarketSessionConfig()
    ts = localize_or_convert_timestamp(timestamp, timezone=cfg.timezone)
    return ts.time() == cfg.market_open


def is_session_end(
    timestamp: pd.Timestamp | str,
    config: Optional[MarketSessionConfig] = None,
) -> bool:
    """True only for the bar stamped exactly at market close."""
    cfg = config or MarketSessionConfig()
    ts = localize_or_convert_timestamp(timestamp, timezone=cfg.timezone)
    return ts.time() == cfg.market_close


def is_same_session(
    ts1: pd.Timestamp | str,
    ts2: pd.Timestamp | str,
    timezone: str = DEFAULT_TIMEZONE,
) -> bool:
    """Check whether two timestamps belong to the same local market session date."""
    return get_session_date(ts1, timezone=timezone) == get_session_date(ts2, timezone=timezone)


def add_session_columns(
    df: pd.DataFrame,
    timestamp_col: str = "timestamp",
    timezone: str = DEFAULT_TIMEZONE,
) -> pd.DataFrame:
    """
    Add useful session-aware columns to a DataFrame:
    - session_timestamp
    - session_date
    - is_market_open_bar
    - is_market_close_bar
    - in_market_hours
    """
    if timestamp_col not in df.columns:
        raise MarketSessionError(f"Missing timestamp column: {timestamp_col}")

    out = df.copy()
    out["session_timestamp"] = pd.to_datetime(out[timestamp_col])

    if getattr(out["session_timestamp"].dt, "tz", None) is None:
        out["session_timestamp"] = out["session_timestamp"].dt.tz_localize(timezone)
    else:
        out["session_timestamp"] = out["session_timestamp"].dt.tz_convert(timezone)

    out["session_date"] = out["session_timestamp"].dt.normalize()
    cfg = MarketSessionConfig(timezone=timezone)

    out["in_market_hours"] = out["session_timestamp"].apply(lambda ts: is_market_open(ts, cfg))
    out["is_market_open_bar"] = out["session_timestamp"].apply(lambda ts: is_session_start(ts, cfg))
    out["is_market_close_bar"] = out["session_timestamp"].apply(lambda ts: is_session_end(ts, cfg))

    return out


def filter_market_hours(
    df: pd.DataFrame,
    timestamp_col: str = "timestamp",
    timezone: str = DEFAULT_TIMEZONE,
) -> pd.DataFrame:
    """Keep only rows within NSE session hours."""
    out = add_session_columns(df, timestamp_col=timestamp_col, timezone=timezone)
    out = out[out["in_market_hours"]].copy()
    return out.reset_index(drop=True)