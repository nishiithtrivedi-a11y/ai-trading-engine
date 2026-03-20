from __future__ import annotations

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal
from src.strategies.breakout import BreakoutStrategy
from src.strategies.intraday_trend_following_strategy import (
    IntradayTrendFollowingStrategy,
    StrategyConfig as IntradayStrategyConfig,
    prepare_strategy_dataframe,
)
from src.strategies.rsi_reversion import RSIReversionStrategy
from src.strategies.sma_crossover import SMACrossoverStrategy


def _make_ohlcv(close_values: list[float]) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(close_values), freq="D", name="timestamp")
    rows = []
    for close in close_values:
        rows.append(
            {
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 10_000.0,
            }
        )
    return pd.DataFrame(rows, index=index)


class _DummyBuyStrategy(BaseStrategy):
    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return Signal.BUY


class _DummyHoldStrategy(BaseStrategy):
    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return Signal.HOLD


def _ist_to_utc(date_str: str, hhmm: str) -> pd.Timestamp:
    return pd.Timestamp(f"{date_str} {hhmm}:00", tz="Asia/Kolkata").tz_convert("UTC")


def _intraday_bars(
    *,
    date_str: str,
    session_start_ist: str = "09:30",
    n_bars: int = 60,
    step: float = 10.0,
    base_price: float = 1000.0,
) -> pd.DataFrame:
    start_ts = _ist_to_utc(date_str, session_start_ist)
    idx = pd.date_range(start=start_ts, periods=n_bars, freq="5min")
    prices = [base_price + i * step for i in range(n_bars)]
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p + 1.0 for p in prices],
            "low": [p - 1.0 for p in prices],
            "close": prices,
            "volume": [10_000.0] * n_bars,
        },
        index=idx,
    )


def test_base_strategy_generate_signal_wraps_on_bar() -> None:
    strategy = _DummyBuyStrategy()
    data = _make_ohlcv([100, 101, 102])
    bar = data.iloc[-1]

    signal = strategy.generate_signal(data, bar, len(data) - 1, symbol="RELIANCE.NS", timeframe="1D")

    assert isinstance(signal, StrategySignal)
    assert signal.action == Signal.BUY
    assert signal.strategy_name == "_DummyBuyStrategy"
    assert signal.symbol == "RELIANCE.NS"
    assert signal.timeframe == "1D"


def test_generate_signals_returns_empty_on_hold() -> None:
    strategy = _DummyHoldStrategy()
    data = _make_ohlcv([100, 101, 102])
    bar = data.iloc[-1]
    signals = strategy.generate_signals(data, bar, len(data) - 1)
    assert signals == []


def test_generate_signals_returns_single_item_on_actionable_signal() -> None:
    strategy = _DummyBuyStrategy()
    data = _make_ohlcv([100, 101, 102])
    bar = data.iloc[-1]
    signals = strategy.generate_signals(data, bar, len(data) - 1)
    assert len(signals) == 1
    assert signals[0].action == Signal.BUY


def test_signal_normalization_supports_enum_structured_and_string() -> None:
    enum_value = BaseStrategy.normalize_signal(Signal.BUY)
    structured_value = BaseStrategy.normalize_signal(
        StrategySignal(action=Signal.EXIT, strategy_name="Example")
    )
    string_value = BaseStrategy.normalize_signal("sell")

    assert enum_value == Signal.BUY
    assert structured_value == Signal.EXIT
    assert string_value == Signal.SELL


def test_sma_strategy_standard_contract_hold_buy_exit_paths() -> None:
    strategy = SMACrossoverStrategy(fast_period=2, slow_period=3)
    strategy.initialize()

    hold_data = _make_ohlcv([10, 10, 10])
    hold_signal = strategy.generate_signal(hold_data, hold_data.iloc[-1], len(hold_data) - 1)
    assert hold_signal.action == Signal.HOLD

    buy_data = _make_ohlcv([10, 10, 10, 11])
    buy_signal = strategy.generate_signal(buy_data, buy_data.iloc[-1], len(buy_data) - 1)
    assert buy_signal.action == Signal.BUY
    assert buy_signal.metadata["fast_period"] == 2

    exit_data = _make_ohlcv([11, 11, 11, 10])
    exit_signal = strategy.generate_signal(exit_data, exit_data.iloc[-1], len(exit_data) - 1)
    assert exit_signal.action == Signal.EXIT


def test_rsi_strategy_standard_contract_hold_buy_exit_paths() -> None:
    strategy = RSIReversionStrategy(rsi_period=5, oversold=30, overbought=70)
    strategy.initialize()

    hold_data = _make_ohlcv([10, 10, 10, 10, 10, 10, 10])
    hold_signal = strategy.generate_signal(hold_data, hold_data.iloc[-1], len(hold_data) - 1)
    assert hold_signal.action == Signal.HOLD

    buy_data = _make_ohlcv([10, 9, 8, 7, 6, 5, 4])
    buy_signal = strategy.generate_signal(buy_data, buy_data.iloc[-1], len(buy_data) - 1)
    assert buy_signal.action == Signal.BUY

    exit_data = _make_ohlcv([1, 2, 3, 4, 5, 6, 7])
    exit_signal = strategy.generate_signal(exit_data, exit_data.iloc[-1], len(exit_data) - 1)
    assert exit_signal.action == Signal.EXIT


def test_breakout_strategy_standard_contract_hold_buy_exit_paths() -> None:
    strategy = BreakoutStrategy(entry_period=3, exit_period=2)
    strategy.initialize()

    hold_data = _make_ohlcv([100, 101, 102, 101.5])
    hold_signal = strategy.generate_signal(hold_data, hold_data.iloc[-1], len(hold_data) - 1)
    assert hold_signal.action == Signal.HOLD

    buy_data = _make_ohlcv([100, 101, 102, 103.5])
    buy_signal = strategy.generate_signal(buy_data, buy_data.iloc[-1], len(buy_data) - 1)
    assert buy_signal.action == Signal.BUY

    exit_data = _make_ohlcv([103, 102, 101, 99.0])
    exit_signal = strategy.generate_signal(exit_data, exit_data.iloc[-1], len(exit_data) - 1)
    assert exit_signal.action == Signal.EXIT


def test_intraday_strategy_standard_contract_buy_and_sell_paths() -> None:
    params = {
        "st_period": 5,
        "ema_length": 5,
        "st_factor": 3.0,
        "session_start": "09:30",
        "session_end": "15:00",
        "timezone": "Asia/Kolkata",
    }
    strategy = IntradayTrendFollowingStrategy(**params)
    strategy.initialize()

    uptrend = _intraday_bars(date_str="2026-01-20", step=10.0, n_bars=60)
    cfg = IntradayStrategyConfig(**strategy.get_params())
    prepared_up = prepare_strategy_dataframe(uptrend, cfg)
    up_candidates = prepared_up[prepared_up["long_signal"]]
    assert not up_candidates.empty

    up_idx = up_candidates.index[-1]
    up_window = uptrend.loc[:up_idx]
    buy_signal = strategy.generate_signal(up_window, up_window.iloc[-1], len(up_window) - 1)
    assert buy_signal.action == Signal.BUY

    n_warm, n_down = 20, 46
    start = _ist_to_utc("2026-01-21", "09:30")
    idx = pd.date_range(start=start, periods=n_warm + n_down, freq="5min")
    prices = [2000.0] * n_warm + [1960.0 - i * 5 for i in range(n_down)]
    downtrend = pd.DataFrame(
        {
            "open": [p + 1 for p in prices],
            "high": [p + 1 for p in prices],
            "low": [p - 1 for p in prices],
            "close": [p - 1 for p in prices],
            "volume": [10_000.0] * (n_warm + n_down),
        },
        index=idx,
    )
    prepared_down = prepare_strategy_dataframe(downtrend, cfg)
    down_candidates = prepared_down[prepared_down["short_signal"]]
    assert not down_candidates.empty

    down_idx = down_candidates.index[-1]
    down_window = downtrend.loc[:down_idx]
    sell_signal = strategy.generate_signal(down_window, down_window.iloc[-1], len(down_window) - 1)
    assert sell_signal.action == Signal.SELL
