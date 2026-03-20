from __future__ import annotations

import pandas as pd

from src.strategies.base_strategy import Signal
from src.strategies.intraday.day_high_low_breakout import DayHighLowBreakoutStrategy
from src.strategies.intraday.opening_range_breakout import OpeningRangeBreakoutStrategy
from src.strategies.intraday.vwap_pullback_trend import VWAPPullbackTrendStrategy


def _ist_to_utc(date_str: str, hhmm: str) -> pd.Timestamp:
    return pd.Timestamp(f"{date_str} {hhmm}:00", tz="Asia/Kolkata").tz_convert("UTC")


def test_opening_range_breakout_emits_buy_on_range_break() -> None:
    start = _ist_to_utc("2026-03-02", "09:15")
    idx = pd.date_range(start=start, periods=12, freq="5min")

    rows = []
    for i in range(12):
        if i < 6:
            close = 100.0
            high = 100.2
            low = 99.8
        else:
            close = 101.0 if i == 6 else 101.2
            high = close + 0.2
            low = close - 0.2
        rows.append(
            {
                "open": close - 0.1,
                "high": high,
                "low": low,
                "close": close,
                "volume": 10_000.0,
            }
        )
    data = pd.DataFrame(rows, index=idx)

    strategy = OpeningRangeBreakoutStrategy()
    strategy.initialize()
    signal = strategy.generate_signal(data, data.iloc[-1], len(data) - 1)
    assert signal.action == Signal.BUY


def test_vwap_pullback_trend_emits_buy_on_reclaim() -> None:
    idx = pd.date_range("2026-03-03 03:45:00+00:00", periods=12, freq="5min")
    close = [100.0, 100.0, 100.1, 100.1, 100.0, 100.0, 99.9, 100.0, 100.1, 100.0, 100.1, 100.4]
    data = pd.DataFrame(
        {
            "open": [c - 0.05 for c in close],
            "high": [c + 0.15 for c in close],
            "low": [c - 0.15 for c in close],
            "close": close,
            "volume": [10_000.0] * len(close),
        },
        index=idx,
    )

    strategy = VWAPPullbackTrendStrategy(direction="long", pullback_tolerance_pct=0.01)
    strategy.initialize()
    signal = strategy.generate_signal(data, data.iloc[-1], len(data) - 1)
    assert signal.action == Signal.BUY


def test_day_high_low_breakout_emits_buy_for_day_high_break() -> None:
    start = _ist_to_utc("2026-03-04", "09:15")
    idx = pd.date_range(start=start, periods=10, freq="5min")
    rows = []
    for i in range(10):
        close = 100.0 + i * 0.1
        if i == 9:
            close = 102.0
        rows.append(
            {
                "open": close - 0.1,
                "high": close + 0.1,
                "low": close - 0.2,
                "close": close,
                "volume": 8_000.0,
            }
        )
    data = pd.DataFrame(rows, index=idx)

    strategy = DayHighLowBreakoutStrategy(direction="long", min_bars_in_session=4)
    strategy.initialize()
    signal = strategy.generate_signal(data, data.iloc[-1], len(data) - 1)
    assert signal.action == Signal.BUY

