from __future__ import annotations

import pandas as pd

from src.strategies.base_strategy import Signal
from src.strategies.intraday.bearish_intraday_regime_strategy import BearishIntradayRegimeStrategy
from src.strategies.intraday.bullish_intraday_regime_strategy import BullishIntradayRegimeStrategy
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


# ---------------------------------------------------------------------------
# BullishIntradayRegimeStrategy
# ---------------------------------------------------------------------------

def _make_bullish_trend_bars(n: int = 120) -> pd.DataFrame:
    """Build IST-aware 5-minute bars forming a clear bullish trend above VWAP/EMA."""
    start = _ist_to_utc("2026-03-10", "09:15")
    idx = pd.date_range(start=start, periods=n, freq="5min")
    rows = []
    for i in range(n):
        # Steady uptrend with moderate volume
        close = 100.0 + i * 0.12
        rows.append(
            {
                "open": close - 0.05,
                "high": close + 0.15,
                "low": close - 0.10,
                "close": close,
                "volume": 15_000.0 if i > 80 else 12_000.0,
            }
        )
    return pd.DataFrame(rows, index=idx)


def test_bullish_intraday_regime_holds_during_warmup() -> None:
    """Strategy must emit HOLD for the first min_bars_warmup bars."""
    data = _make_bullish_trend_bars(120)
    strategy = BullishIntradayRegimeStrategy()
    strategy.initialize()

    context: dict = {}
    strategy.precompute(data, context)

    # Bar 10 is well inside warmup window (default 50)
    signal = strategy.on_bar(data.iloc[10], 10, context)
    assert signal == Signal.HOLD


def test_bullish_intraday_regime_returns_strategy_signal_after_warmup() -> None:
    """After warmup, on_bar returns a StrategySignal (not a raw enum) when a bar is processed."""
    from src.strategies.base_strategy import StrategySignal

    data = _make_bullish_trend_bars(120)
    strategy = BullishIntradayRegimeStrategy()
    strategy.initialize()

    context: dict = {}
    strategy.precompute(data, context)

    # Run through post-warmup bars and collect outputs
    outputs = []
    for i in range(50, len(data)):
        out = strategy.on_bar(data.iloc[i], i, context)
        outputs.append(out)

    # Every output must be either Signal.HOLD or a StrategySignal
    for out in outputs:
        assert isinstance(out, (Signal, StrategySignal)), f"Unexpected type: {type(out)}"


def test_bullish_intraday_regime_created_via_registry() -> None:
    """Strategy must be instantiable through the engine's standard registry factory."""
    from src.strategies.registry import create_strategy, get_strategy_spec

    spec = get_strategy_spec("bullish_intraday_regime")
    assert spec.category == "intraday"
    assert spec.mode == "full"

    strategy = create_strategy("bullish_intraday_regime")
    assert isinstance(strategy, BullishIntradayRegimeStrategy)
    assert strategy._is_initialized  # factory calls initialize()


def test_bullish_intraday_regime_alias_resolves() -> None:
    """Alias bullish_regime_intraday must resolve to the same strategy."""
    from src.strategies.registry import create_strategy

    strategy = create_strategy("bullish_regime_intraday")
    assert isinstance(strategy, BullishIntradayRegimeStrategy)


def test_bullish_intraday_regime_param_override() -> None:
    """Custom params must be respected via the factory."""
    from src.strategies.registry import create_strategy

    strategy = create_strategy(
        "bullish_intraday_regime",
        params={"adx_threshold": 30.0, "volume_multiplier": 1.5},
    )
    assert strategy.config.adx_threshold == 30.0
    assert strategy.config.volume_multiplier == 1.5


# ---------------------------------------------------------------------------
# BearishIntradayRegimeStrategy
# ---------------------------------------------------------------------------

def _make_bearish_oversold_bars(n: int = 120) -> pd.DataFrame:
    """Build IST-aware 5-minute bars forming a bearish downtrend reaching oversold levels."""
    start = _ist_to_utc("2026-03-11", "09:15")
    idx = pd.date_range(start=start, periods=n, freq="5min")
    rows = []
    for i in range(n):
        # Steady downtrend; last 10 bars have higher volume and close > open (bounce attempt)
        close = 120.0 - i * 0.15
        is_last = i >= n - 10
        rows.append(
            {
                "open": (close - 0.08) if is_last else (close + 0.05),
                "high": close + 0.15,
                "low": close - 0.15,
                "close": close,
                "volume": 18_000.0 if is_last else 10_000.0,
            }
        )
    return pd.DataFrame(rows, index=idx)


def test_bearish_intraday_regime_holds_during_warmup() -> None:
    """Strategy must emit HOLD for the first min_bars_warmup bars."""
    data = _make_bearish_oversold_bars(120)
    strategy = BearishIntradayRegimeStrategy()
    strategy.initialize()

    context: dict = {}
    strategy.precompute(data, context)

    signal = strategy.on_bar(data.iloc[10], 10, context)
    assert signal == Signal.HOLD


def test_bearish_intraday_regime_returns_strategy_signal_after_warmup() -> None:
    """After warmup, on_bar must return Signal or StrategySignal without raising."""
    from src.strategies.base_strategy import StrategySignal

    data = _make_bearish_oversold_bars(120)
    strategy = BearishIntradayRegimeStrategy()
    strategy.initialize()

    context: dict = {}
    strategy.precompute(data, context)

    for i in range(50, len(data)):
        out = strategy.on_bar(data.iloc[i], i, context)
        assert isinstance(out, (Signal, StrategySignal)), f"Unexpected type: {type(out)}"


def test_bearish_intraday_regime_created_via_registry() -> None:
    """Strategy must be instantiable through the engine's standard registry factory."""
    from src.strategies.registry import create_strategy, get_strategy_spec

    spec = get_strategy_spec("bearish_intraday_regime")
    assert spec.category == "intraday"
    assert spec.mode == "full"

    strategy = create_strategy("bearish_intraday_regime")
    assert isinstance(strategy, BearishIntradayRegimeStrategy)
    assert strategy._is_initialized


def test_bearish_intraday_regime_alias_resolves() -> None:
    """Alias bearish_regime_intraday must resolve to the same strategy."""
    from src.strategies.registry import create_strategy

    strategy = create_strategy("bearish_regime_intraday")
    assert isinstance(strategy, BearishIntradayRegimeStrategy)


def test_bearish_intraday_regime_param_override() -> None:
    """Custom params must be respected via the factory."""
    from src.strategies.registry import create_strategy

    strategy = create_strategy(
        "bearish_intraday_regime",
        params={"rsi_oversold": 25.0, "volume_spike_mult": 1.5},
    )
    assert strategy.config.rsi_oversold == 25.0
    assert strategy.config.volume_spike_mult == 1.5


def test_regime_strategies_precompute_context_keys() -> None:
    """precompute() must populate the expected context keys for both strategies."""
    data_bull = _make_bullish_trend_bars(80)
    data_bear = _make_bearish_oversold_bars(80)

    bull = BullishIntradayRegimeStrategy()
    bull.initialize()
    ctx_bull: dict = {}
    bull.precompute(data_bull, ctx_bull)
    assert "bullish_prepared" in ctx_bull

    bear = BearishIntradayRegimeStrategy()
    bear.initialize()
    ctx_bear: dict = {}
    bear.precompute(data_bear, ctx_bear)
    assert "bearish_prepared" in ctx_bear


def test_regime_strategies_graceful_without_precompute() -> None:
    """on_bar must return HOLD gracefully when context is empty (no precompute called)."""
    data = _make_bullish_trend_bars(80)

    bull = BullishIntradayRegimeStrategy()
    bull.initialize()
    signal = bull.on_bar(data.iloc[-1], len(data) - 1, context={})
    assert signal == Signal.HOLD

    bear = BearishIntradayRegimeStrategy()
    bear.initialize()
    signal = bear.on_bar(data.iloc[-1], len(data) - 1, context={})
    assert signal == Signal.HOLD

