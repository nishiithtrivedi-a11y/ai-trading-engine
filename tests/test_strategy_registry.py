from __future__ import annotations

import pytest

from src.strategies.base_strategy import BaseStrategy
from src.strategies.registry import (
    UnsupportedStrategyError,
    create_strategy,
    get_strategy_class,
    get_strategy_registry,
    resolve_package,
    resolve_strategy,
)
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


def test_resolve_strategy_exact_match() -> None:
    spec = resolve_strategy("sma_crossover")
    assert spec.key == "sma_crossover"
    assert spec.strategy_class is SMACrossoverStrategy


def test_resolve_strategy_alias_match() -> None:
    spec = resolve_strategy("dual_moving_average_crossover")
    assert spec.key == "sma_crossover"


def test_resolve_strategy_fuzzy_match() -> None:
    with pytest.raises(ValueError, match="Unknown strategy 'sma_cross'. Did you mean: 'sma_crossover'?"):
        resolve_strategy("sma_cross")


def test_resolve_strategy_not_found() -> None:
    with pytest.raises(ValueError, match="Unknown strategy"):
        resolve_strategy("totally_fake_strategy_name")


def test_resolve_package_exact_category() -> None:
    specs = resolve_package("intraday")
    assert len(specs) > 0
    assert all(s.category == "intraday" for s in specs)
    keys = {s.key for s in specs}
    assert "intraday_trend_following" in keys


def test_resolve_package_fuzzy_category() -> None:
    with pytest.raises(ValueError, match="Unknown package 'commo'. Did you mean: 'commodities'?"):
        resolve_package("commo")


def test_resolve_package_all() -> None:
    with pytest.raises(ValueError, match="Unknown package 'all'."):
        resolve_package("all")


def test_resolve_package_not_found() -> None:
    with pytest.raises(ValueError, match="Unknown package"):
        resolve_package("fake_package_name_xyz")
