from __future__ import annotations

import pytest

from src.strategies.base_strategy import BaseStrategy
from src.strategies.registry import create_strategy, get_strategy_class, get_strategy_registry
from src.strategies.sma_crossover import SMACrossoverStrategy


def test_strategy_registry_contains_expected_entries() -> None:
    registry = get_strategy_registry()
    expected = {"sma_crossover", "rsi_reversion", "breakout", "intraday_trend_following"}
    assert expected.issubset(set(registry.keys()))


def test_get_strategy_class_returns_base_strategy_subclass() -> None:
    strategy_cls = get_strategy_class("sma_crossover")
    assert issubclass(strategy_cls, BaseStrategy)
    assert strategy_cls is SMACrossoverStrategy


def test_create_strategy_initializes_instance_with_params() -> None:
    strategy = create_strategy(
        "sma_crossover",
        params={"fast_period": 5, "slow_period": 20},
    )
    assert isinstance(strategy, SMACrossoverStrategy)
    assert strategy.config.fast_period == 5
    assert strategy.config.slow_period == 20


def test_create_strategy_raises_for_unknown_name() -> None:
    with pytest.raises(ValueError, match="Unknown strategy"):
        create_strategy("does_not_exist")
