"""Tests for the ExecutionEngine module."""

from datetime import datetime

import pandas as pd
import pytest

from src.core.execution import ExecutionEngine
from src.core.order import Order, OrderType, OrderSide


def make_bar(open_: float, high: float, low: float, close: float) -> pd.Series:
    return pd.Series({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 10000,
    })


class TestExecutionEngine:

    def test_market_buy_fills_at_open_plus_slippage(self):
        engine = ExecutionEngine(fee_rate=0.001, slippage_rate=0.001)
        order = Order(
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
            signal_price=100.0,
            timestamp=datetime(2023, 1, 1),
        )
        bar = make_bar(100.0, 102.0, 99.0, 101.0)
        fill = engine.calculate_fill_price(order, bar)
        assert fill == pytest.approx(100.1)  # 100 + 100*0.001

    def test_market_sell_fills_at_open_minus_slippage(self):
        engine = ExecutionEngine(fee_rate=0.001, slippage_rate=0.001)
        order = Order(
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=100,
            signal_price=100.0,
            timestamp=datetime(2023, 1, 1),
        )
        bar = make_bar(100.0, 102.0, 99.0, 101.0)
        fill = engine.calculate_fill_price(order, bar)
        assert fill == pytest.approx(99.9)  # 100 - 100*0.001

    def test_limit_buy_fills_when_price_reaches_limit(self):
        engine = ExecutionEngine(fee_rate=0.001, slippage_rate=0.0)
        order = Order(
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            signal_price=100.0,
            timestamp=datetime(2023, 1, 1),
            limit_price=98.0,
        )
        bar = make_bar(99.0, 100.0, 97.0, 99.5)  # Low hits 97 < 98
        fill = engine.calculate_fill_price(order, bar)
        assert fill == 98.0  # min(open=99, limit=98) = 98

    def test_limit_buy_no_fill_when_price_doesnt_reach(self):
        engine = ExecutionEngine(fee_rate=0.001, slippage_rate=0.0)
        order = Order(
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            signal_price=100.0,
            timestamp=datetime(2023, 1, 1),
            limit_price=95.0,
        )
        bar = make_bar(99.0, 100.0, 97.0, 99.5)  # Low is 97 > 95 — doesn't reach
        fill = engine.calculate_fill_price(order, bar)
        # Actually 97 > 95 is false, 97 is greater than 95
        # Wait: the condition is bar["low"] <= limit_price => 97 <= 95 => False
        assert fill is None

    def test_fee_calculation(self):
        engine = ExecutionEngine(fee_rate=0.001)
        fees = engine.calculate_fees(100.0, 50)
        assert fees == pytest.approx(5.0)  # 100 * 50 * 0.001

    def test_execute_order_fills_and_updates(self):
        engine = ExecutionEngine(fee_rate=0.001, slippage_rate=0.0005)
        order = Order(
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
            signal_price=50.0,
            timestamp=datetime(2023, 1, 1),
        )
        bar = make_bar(50.0, 52.0, 49.0, 51.0)
        result = engine.execute_order(order, bar, datetime(2023, 1, 2))

        assert result is True
        assert order.is_filled
        assert order.fill_price == pytest.approx(50.025)  # 50 + 50*0.0005
        assert order.fees == pytest.approx(50.025 * 100 * 0.001)

    def test_zero_slippage(self):
        engine = ExecutionEngine(fee_rate=0.0, slippage_rate=0.0)
        order = Order(
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
            signal_price=100.0,
            timestamp=datetime(2023, 1, 1),
        )
        bar = make_bar(100.0, 102.0, 99.0, 101.0)
        fill = engine.calculate_fill_price(order, bar)
        assert fill == 100.0
