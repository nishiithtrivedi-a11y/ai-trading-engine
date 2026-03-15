"""
Generate synthetic intraday 5-minute OHLCV CSV files for strategy testing.

Produces three CSV files in data/:
  intraday_uptrend_5m.csv   – strong uptrend (for long-signal tests)
  intraday_downtrend_5m.csv – gap-down then downtrend (for short-signal tests)
  intraday_flat_5m.csv      – flat / sideways (for no-trade tests)

All timestamps are UTC-aware (matching RELIANCE_5M.csv format).
IST session: 09:30–15:00 → UTC 04:00–09:30 for 5M bars.
"""

from __future__ import annotations

import os
import pandas as pd
import numpy as np


def _ist_to_utc(date_str: str, hhmm: str) -> pd.Timestamp:
    ts = pd.Timestamp(f"{date_str} {hhmm}:00", tz="Asia/Kolkata")
    return ts.tz_convert("UTC")


def _make_session_bars(
    date_str: str,
    session_start_ist: str,
    n_bars: int,
    freq: str,
    prices: list[float],
    bar_range: float = 2.0,
    volume: int = 10_000,
) -> pd.DataFrame:
    start_ts = _ist_to_utc(date_str, session_start_ist)
    idx = pd.date_range(start=start_ts, periods=n_bars, freq=freq)
    half = bar_range / 2.0
    return pd.DataFrame(
        {
            "timestamp": idx.astype(str),
            "open":      [p for p in prices],
            "high":      [p + half for p in prices],
            "low":       [p - half for p in prices],
            "close":     [p for p in prices],
            "volume":    [volume] * n_bars,
        }
    )


def generate_uptrend(out_path: str, days: int = 3) -> None:
    """
    Multi-day strong uptrend starting at 09:15 IST each day.
    Pre-session bars (09:15–09:25) for warmup + in-session bars (09:30–14:55).
    """
    frames = []
    trading_dates = pd.bdate_range("2025-12-10", periods=days, freq="B")
    base_price = 1000.0

    for day in trading_dates:
        date_str = str(day.date())
        # 5 pre-session bars (09:15–09:25) for ATR/EMA warmup
        n_pre = 3
        n_session = 66   # 09:30–14:55 IST (66 × 5min)
        n_total = n_pre + n_session
        prices = [base_price + i * 10.0 for i in range(n_total)]

        bars = _make_session_bars(
            date_str, "09:15", n_total, "5min", prices, bar_range=2.0
        )
        frames.append(bars)
        base_price += n_total * 10.0  # next day starts from where today ended

    df = pd.concat(frames, ignore_index=True)
    df.to_csv(out_path, index=False)
    print(f"Written: {out_path}  ({len(df)} bars)")


def generate_downtrend(out_path: str, days: int = 3) -> None:
    """
    Multi-day scenario:
      - Warmup bars (sideways at 2000) for ATR/EMA/SuperTrend initialization
      - Then gap-down and persistent downtrend within each session
    NOTE: Short signals may still not fire due to BUG 1 (SuperTrend NaN issue).
    """
    frames = []
    trading_dates = pd.bdate_range("2025-12-10", periods=days, freq="B")

    for day in trading_dates:
        date_str = str(day.date())
        # 20 warmup bars sideways at 2000
        n_warm = 20
        n_down = 46
        n_total = n_warm + n_down

        warm_prices = [2000.0] * n_warm
        down_prices = [1960.0 - i * 5.0 for i in range(n_down)]
        prices = warm_prices + down_prices

        bars = _make_session_bars(
            date_str, "09:30", n_total, "5min", prices, bar_range=2.0
        )
        frames.append(bars)

    df = pd.concat(frames, ignore_index=True)
    df.to_csv(out_path, index=False)
    print(f"Written: {out_path}  ({len(df)} bars)")


def generate_flat(out_path: str, days: int = 3) -> None:
    """
    Flat/sideways data: price never moves far from VWAP.
    Designed so no long or short signal should fire (close ≈ VWAP always).
    Also includes pre-session (out-of-window) bars to verify session filter.
    """
    frames = []
    trading_dates = pd.bdate_range("2025-12-10", periods=days, freq="B")

    for day in trading_dates:
        date_str = str(day.date())
        # Pre-session bars (00:00–04:00 IST) – outside session window
        n_pre = 10
        pre_prices = [1500.0] * n_pre
        pre_bars = _make_session_bars(
            date_str, "00:00", n_pre, "5min", pre_prices, bar_range=0.5
        )
        frames.append(pre_bars)

        # In-session bars (09:30–14:55) – flat around 1500
        rng = np.random.default_rng(seed=42)
        n_sess = 66
        noise = rng.uniform(-0.1, 0.1, n_sess)
        sess_prices = [1500.0 + n for n in noise]
        sess_bars = _make_session_bars(
            date_str, "09:30", n_sess, "5min", sess_prices, bar_range=0.5
        )
        frames.append(sess_bars)

    df = pd.concat(frames, ignore_index=True)
    df.to_csv(out_path, index=False)
    print(f"Written: {out_path}  ({len(df)} bars)")


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    generate_uptrend("data/intraday_uptrend_5m.csv", days=3)
    generate_downtrend("data/intraday_downtrend_5m.csv", days=3)
    generate_flat("data/intraday_flat_5m.csv", days=3)
    print("\nAll synthetic datasets generated.")
