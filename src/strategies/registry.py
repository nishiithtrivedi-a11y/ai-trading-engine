"""
Central strategy registry helpers.

This module provides a small shared registry for strategy discovery and
construction. It is intentionally lightweight and execution-agnostic.
"""

from __future__ import annotations

from typing import Any

from src.strategies.base_strategy import BaseStrategy
from src.strategies.breakout import BreakoutStrategy
from src.strategies.intraday_trend_following_strategy import IntradayTrendFollowingStrategy
from src.strategies.rsi_reversion import RSIReversionStrategy
from src.strategies.sma_crossover import SMACrossoverStrategy

StrategyClass = type[BaseStrategy]


_DEFAULT_REGISTRY: dict[str, StrategyClass] = {
    "sma_crossover": SMACrossoverStrategy,
    "rsi_reversion": RSIReversionStrategy,
    "breakout": BreakoutStrategy,
    "intraday_trend_following": IntradayTrendFollowingStrategy,
}


def get_strategy_registry() -> dict[str, StrategyClass]:
    """Return a copy of the built-in strategy registry."""
    return dict(_DEFAULT_REGISTRY)


def get_strategy_class(name: str) -> StrategyClass:
    """Resolve a strategy class by registry key."""
    key = str(name).strip().lower()
    try:
        return _DEFAULT_REGISTRY[key]
    except KeyError as exc:
        available = ", ".join(sorted(_DEFAULT_REGISTRY.keys()))
        raise ValueError(
            f"Unknown strategy '{name}'. Available strategies: {available}"
        ) from exc


def create_strategy(
    name: str,
    *,
    params: dict[str, Any] | None = None,
) -> BaseStrategy:
    """
    Instantiate a registered strategy with optional parameters.

    Initialization is called so the returned object is immediately runnable.
    """
    strategy_cls = get_strategy_class(name)
    strategy_params = dict(params or {})
    instance = strategy_cls(**strategy_params)
    instance.initialize(strategy_params)
    return instance

