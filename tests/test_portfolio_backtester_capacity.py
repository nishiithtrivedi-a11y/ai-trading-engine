"""
Regression tests for PortfolioBacktester capital-allocation modes.

These tests lock in the two supported behaviours introduced in the Phase 16A
stabilisation pass:

  reserve_full_capacity=False (default)
    per_symbol_capital = initial_capital / num_active_symbols

  reserve_full_capacity=True (conservative reserve mode)
    per_symbol_capital = initial_capital / max_positions

Before the fix the denominator was always max_positions, leaving capital idle
when fewer symbols were active.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.core.data_handler import DataHandler
from src.research.portfolio_backtester import PortfolioBacktester
from src.strategies.base_strategy import BaseStrategy, Signal
from src.utils.config import BacktestConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 60, start_price: float = 100.0) -> pd.DataFrame:
    """Return a minimal OHLCV DataFrame with a flat price series."""
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    price = start_price
    return pd.DataFrame(
        {
            "open": [price] * n,
            "high": [price + 1.0] * n,
            "low": [price - 1.0] * n,
            "close": [price] * n,
            "volume": [10_000.0] * n,
        },
        index=dates,
    )


class NeverTradeStrategy(BaseStrategy):
    """Always returns HOLD so positions never open; equity stays flat."""

    def on_bar(
        self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int
    ) -> Signal:
        return Signal.HOLD


def _registry() -> dict:
    return {"never": {"class": NeverTradeStrategy, "params": {}}}


def _backtester(
    num_symbols: int,
    max_positions: int,
    reserve_full_capacity: bool,
    initial_capital: float = 30_000.0,
) -> PortfolioBacktester:
    symbol_to_data = {
        f"SYM{i}.NS": DataHandler(_make_ohlcv())
        for i in range(num_symbols)
    }
    base_cfg = BacktestConfig(initial_capital=initial_capital)
    return PortfolioBacktester(
        base_config=base_cfg,
        strategy_registry=_registry(),
        symbol_to_data=symbol_to_data,
        max_positions=max_positions,
        reserve_full_capacity=reserve_full_capacity,
        output_dir="output/test_capacity",
    )


# ---------------------------------------------------------------------------
# Tests — default mode (reserve_full_capacity=False)
# ---------------------------------------------------------------------------

class TestDefaultCapacityMode:
    """When reserve_full_capacity is False (default), capital is divided
    across the actual active symbols, not max_positions."""

    def test_per_symbol_capital_equals_total_divided_by_active_count(self):
        # 3 symbols, max_positions=10 → per-symbol = 30_000 / 3 = 10_000
        bt = _backtester(num_symbols=3, max_positions=10, reserve_full_capacity=False)
        result = bt.run()
        assert result.reserve_full_capacity is False
        assert result.per_symbol_capital == pytest.approx(10_000.0)

    def test_per_symbol_capital_equals_total_when_single_symbol(self):
        # 1 symbol, max_positions=5 → per-symbol = 30_000 / 1 = 30_000
        bt = _backtester(num_symbols=1, max_positions=5, reserve_full_capacity=False)
        result = bt.run()
        assert result.per_symbol_capital == pytest.approx(30_000.0)

    def test_per_symbol_capital_equals_total_divided_by_capped_active_count(self):
        # 5 symbols but max_positions=3 → only 3 active → per-symbol = 30_000/3 = 10_000
        bt = _backtester(num_symbols=5, max_positions=3, reserve_full_capacity=False)
        result = bt.run()
        assert result.num_symbols_active == 3
        assert result.num_symbols_skipped == 2
        assert result.per_symbol_capital == pytest.approx(10_000.0)

    def test_sum_of_allocated_capital_equals_initial_capital(self):
        # per_symbol_capital * num_active == initial_capital
        bt = _backtester(num_symbols=4, max_positions=10, reserve_full_capacity=False)
        result = bt.run()
        total_allocated = result.per_symbol_capital * result.num_symbols_active
        assert total_allocated == pytest.approx(30_000.0)


# ---------------------------------------------------------------------------
# Tests — reserve_full_capacity=True (conservative mode)
# ---------------------------------------------------------------------------

class TestReserveCapacityMode:
    """When reserve_full_capacity is True, per-symbol capital stays fixed at
    initial_capital / max_positions regardless of how many symbols are active."""

    def test_per_symbol_capital_uses_max_positions_as_denominator(self):
        # 3 symbols, max_positions=10 → per-symbol = 30_000 / 10 = 3_000
        bt = _backtester(num_symbols=3, max_positions=10, reserve_full_capacity=True)
        result = bt.run()
        assert result.reserve_full_capacity is True
        assert result.per_symbol_capital == pytest.approx(3_000.0)

    def test_reserve_mode_single_symbol_still_uses_max_positions(self):
        # 1 symbol, max_positions=5 → per-symbol = 30_000 / 5 = 6_000
        bt = _backtester(num_symbols=1, max_positions=5, reserve_full_capacity=True)
        result = bt.run()
        assert result.per_symbol_capital == pytest.approx(6_000.0)

    def test_reserve_mode_produces_smaller_per_symbol_than_default(self):
        # With more max_positions than active symbols, reserve mode is conservative
        default_bt = _backtester(
            num_symbols=2, max_positions=10, reserve_full_capacity=False
        )
        reserve_bt = _backtester(
            num_symbols=2, max_positions=10, reserve_full_capacity=True
        )
        default_result = default_bt.run()
        reserve_result = reserve_bt.run()
        # default: 30_000/2=15_000; reserve: 30_000/10=3_000
        assert default_result.per_symbol_capital > reserve_result.per_symbol_capital

    def test_reserve_mode_when_active_equals_max_positions(self):
        # 3 symbols, max_positions=3 → both modes produce same result
        default_result = _backtester(
            num_symbols=3, max_positions=3, reserve_full_capacity=False
        ).run()
        reserve_result = _backtester(
            num_symbols=3, max_positions=3, reserve_full_capacity=True
        ).run()
        assert default_result.per_symbol_capital == pytest.approx(
            reserve_result.per_symbol_capital
        )


# ---------------------------------------------------------------------------
# Tests — result metadata
# ---------------------------------------------------------------------------

class TestResultMetadata:

    def test_result_echoes_reserve_flag_false(self):
        result = _backtester(2, 5, False).run()
        assert result.reserve_full_capacity is False

    def test_result_echoes_reserve_flag_true(self):
        result = _backtester(2, 5, True).run()
        assert result.reserve_full_capacity is True

    def test_result_echoes_max_positions(self):
        result = _backtester(3, 7, False).run()
        assert result.max_positions == 7

    def test_num_symbols_active_does_not_exceed_max_positions(self):
        result = _backtester(num_symbols=10, max_positions=4, reserve_full_capacity=False).run()
        assert result.num_symbols_active <= 4
        assert result.num_symbols_skipped == 10 - result.num_symbols_active
