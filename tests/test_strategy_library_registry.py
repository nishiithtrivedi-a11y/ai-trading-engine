from __future__ import annotations

import pandas as pd

from src.strategies.base_strategy import StrategySignal
from src.strategies.common import bollinger_bands, rolling_zscore
from src.strategies.registry import (
    create_strategy,
    get_runtime_strategy_registry,
    get_strategies_by_category,
    get_strategy_defaults,
    list_strategy_keys,
)


def _make_ohlcv(rows: int = 320) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=rows, freq="D", name="timestamp")
    close = pd.Series([100.0 + i * 0.2 for i in range(rows)], index=index)
    data = pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 10_000.0,
            "pair_close": close * 0.98,
            "benchmark_close": close * 0.95,
        },
        index=index,
    )
    return data


def test_common_series_utils_return_expected_shapes() -> None:
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    z = rolling_zscore(series, window=3)
    middle, upper, lower = bollinger_bands(series, window=3, num_std=2.0)
    assert len(z) == len(series)
    assert len(middle) == len(series)
    assert len(upper) == len(series)
    assert len(lower) == len(series)


def test_registry_alias_defaults_and_categories() -> None:
    keys = list_strategy_keys()
    assert "sma_crossover" in keys
    assert "opening_range_breakout" in keys
    assert "pairs_zscore_limited" in keys
    assert "codex_intraday_regime_breakout" in keys
    assert "codex_intraday_trend_reentry" in keys
    assert "codex_intraday_range_reversion" in keys

    by_category = get_strategies_by_category()
    assert "intraday" in by_category
    assert "swing" in by_category
    assert "positional" in by_category

    defaults = get_strategy_defaults("dual_moving_average_crossover")
    assert isinstance(defaults, dict)

    strategy = create_strategy("dual_moving_average_crossover")
    assert strategy.__class__.__name__ == "SMACrossoverStrategy"


def test_all_runnable_strategies_can_instantiate_and_generate_signal() -> None:
    runtime_registry = get_runtime_strategy_registry()
    data = _make_ohlcv()
    current_bar = data.iloc[-1]
    bar_index = len(data) - 1

    failures: list[str] = []
    for key in sorted(runtime_registry.keys()):
        try:
            strategy = create_strategy(key)
            signal = strategy.generate_signal(
                data,
                current_bar,
                bar_index,
                symbol="TEST.NS",
                timeframe="1D",
            )
            assert isinstance(signal, StrategySignal)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{key}: {exc}")

    assert not failures, "Runnable strategies failed contract smoke: " + "; ".join(failures)

