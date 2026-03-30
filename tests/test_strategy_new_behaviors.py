from __future__ import annotations

import pandas as pd

from src.strategies.base_strategy import Signal
from src.strategies.intraday.codex_intraday_range_reversion import CodexIntradayRangeReversionStrategy
from src.strategies.intraday.codex_intraday_regime_breakout import CodexIntradayRegimeBreakoutStrategy
from src.strategies.intraday.codex_intraday_trend_reentry import CodexIntradayTrendReentryStrategy
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


def test_codex_intraday_regime_breakout_emits_buy_on_compression_break() -> None:
    start = _ist_to_utc("2026-03-05", "09:15")
    idx = pd.date_range(start=start, periods=62, freq="5min")

    rows = []
    for i in range(62):
        if i < 49:
            close = 100.0 + i * 0.07
            high = close + 0.12
            low = close - 0.12
        elif i < 61:
            close = 103.44 + (i - 49) * 0.003
            high = 103.52
            low = 103.38
        else:
            close = 104.20
            high = 104.35
            low = 104.00
        rows.append(
            {
                "open": close - 0.05,
                "high": high,
                "low": low,
                "close": close,
                "volume": 20_000.0 if i == 61 else 10_000.0,
            }
        )
    data = pd.DataFrame(rows, index=idx)

    strategy = CodexIntradayRegimeBreakoutStrategy()
    strategy.initialize()
    signal = strategy.generate_signal(data, data.iloc[-1], len(data) - 1)
    assert signal.action == Signal.BUY


def test_codex_intraday_trend_reentry_emits_buy_on_reclaim_trigger() -> None:
    start = _ist_to_utc("2026-03-06", "09:15")
    idx = pd.date_range(start=start, periods=60, freq="5min")

    close = []
    for i in range(60):
        if i < 48:
            close.append(100.0 + i * 0.08)
        elif i < 58:
            close.append(103.8 - (i - 48) * 0.08)
        elif i == 58:
            close.append(103.10)
        else:
            close.append(103.85)

    rows = []
    for i, c in enumerate(close):
        rows.append(
            {
                "open": c - 0.04,
                "high": c + (0.20 if i == 59 else 0.12),
                "low": c - 0.18,
                "close": c,
                "volume": 11_500.0 if i == 59 else 10_000.0,
            }
        )
    data = pd.DataFrame(rows, index=idx)

    strategy = CodexIntradayTrendReentryStrategy()
    strategy.initialize()
    signal = strategy.generate_signal(data, data.iloc[-1], len(data) - 1)
    assert signal.action == Signal.BUY


def test_codex_intraday_range_reversion_emits_buy_in_range_regime_pullback() -> None:
    start = _ist_to_utc("2026-03-09", "09:15")
    idx = pd.date_range(start=start, periods=50, freq="5min")

    close = []
    for i in range(45):
        close.append(100.0 + (0.18 if i % 2 == 0 else -0.18))
    close.extend([100.10, 99.90, 99.75, 99.20, 99.40])

    rows = []
    for i, c in enumerate(close):
        rows.append(
            {
                "open": c + 0.02 if i % 2 == 0 else c - 0.02,
                "high": c + 0.14,
                "low": c - 0.14,
                "close": c,
                "volume": 10_500.0 if i == 49 else 10_000.0,
            }
        )
    data = pd.DataFrame(rows, index=idx)

    strategy = CodexIntradayRangeReversionStrategy(oversold_rsi=42.0)
    strategy.initialize()
    signal = strategy.generate_signal(data, data.iloc[-1], len(data) - 1)
    assert signal.action == Signal.BUY

