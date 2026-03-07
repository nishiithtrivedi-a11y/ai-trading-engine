"""Tests for Order and Position modules."""

from datetime import datetime

import pytest

from src.core.order import Order, OrderType, OrderSide, OrderStatus
from src.core.position import Position, PositionSide, Trade


class TestOrder:

    def test_create_market_buy(self):
        order = Order(
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
            signal_price=50.0,
            timestamp=datetime(2023, 1, 1),
        )
        assert order.is_buy
        assert not order.is_sell
        assert order.status == OrderStatus.PENDING

    def test_mark_filled(self):
        order = Order(
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
            signal_price=50.0,
            timestamp=datetime(2023, 1, 1),
        )
        order.mark_filled(50.05, datetime(2023, 1, 2), fees=5.0, slippage=0.05)
        assert order.is_filled
        assert order.fill_price == 50.05
        assert order.fees == 5.0

    def test_mark_cancelled(self):
        order = Order(
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
            signal_price=50.0,
            timestamp=datetime(2023, 1, 1),
        )
        order.mark_cancelled("no cash")
        assert order.status == OrderStatus.CANCELLED
        assert order.reason == "no cash"


class TestPosition:

    def test_unrealized_pnl_long_profit(self):
        pos = Position(
            side=PositionSide.LONG,
            entry_price=100.0,
            quantity=10,
            entry_timestamp=datetime(2023, 1, 1),
        )
        assert pos.unrealized_pnl(110.0) == 100.0  # 10 * (110 - 100)

    def test_unrealized_pnl_long_loss(self):
        pos = Position(
            side=PositionSide.LONG,
            entry_price=100.0,
            quantity=10,
            entry_timestamp=datetime(2023, 1, 1),
        )
        assert pos.unrealized_pnl(90.0) == -100.0

    def test_market_value(self):
        pos = Position(
            side=PositionSide.LONG,
            entry_price=100.0,
            quantity=10,
            entry_timestamp=datetime(2023, 1, 1),
        )
        assert pos.market_value(105.0) == 1050.0

    def test_stop_loss_triggered(self):
        pos = Position(
            side=PositionSide.LONG,
            entry_price=100.0,
            quantity=10,
            entry_timestamp=datetime(2023, 1, 1),
            stop_loss=95.0,
        )
        # Normal stop hit
        exit_price = pos.check_stop_loss(current_low=94.0, current_open=98.0)
        assert exit_price == 95.0

    def test_stop_loss_gap_down(self):
        pos = Position(
            side=PositionSide.LONG,
            entry_price=100.0,
            quantity=10,
            entry_timestamp=datetime(2023, 1, 1),
            stop_loss=95.0,
        )
        # Gap down: opens below stop => fill at open, not stop
        exit_price = pos.check_stop_loss(current_low=90.0, current_open=93.0)
        assert exit_price == 93.0

    def test_stop_loss_not_triggered(self):
        pos = Position(
            side=PositionSide.LONG,
            entry_price=100.0,
            quantity=10,
            entry_timestamp=datetime(2023, 1, 1),
            stop_loss=95.0,
        )
        exit_price = pos.check_stop_loss(current_low=96.0, current_open=99.0)
        assert exit_price is None

    def test_take_profit_triggered(self):
        pos = Position(
            side=PositionSide.LONG,
            entry_price=100.0,
            quantity=10,
            entry_timestamp=datetime(2023, 1, 1),
            take_profit=110.0,
        )
        exit_price = pos.check_take_profit(current_high=112.0, current_open=105.0)
        assert exit_price == 110.0

    def test_take_profit_gap_up(self):
        pos = Position(
            side=PositionSide.LONG,
            entry_price=100.0,
            quantity=10,
            entry_timestamp=datetime(2023, 1, 1),
            take_profit=110.0,
        )
        # Gap up: opens above take profit => fill at open
        exit_price = pos.check_take_profit(current_high=115.0, current_open=112.0)
        assert exit_price == 112.0

    def test_trailing_stop_update(self):
        pos = Position(
            side=PositionSide.LONG,
            entry_price=100.0,
            quantity=10,
            entry_timestamp=datetime(2023, 1, 1),
            trailing_stop_pct=0.05,
        )
        # Price goes up to 110
        pos.update_trailing_stop(110.0)
        assert pos.highest_price == 110.0
        assert pos.stop_loss == pytest.approx(110.0 * 0.95)  # 104.5

        # Price goes up to 120
        pos.update_trailing_stop(120.0)
        assert pos.highest_price == 120.0
        assert pos.stop_loss == pytest.approx(120.0 * 0.95)  # 114.0

        # Price drops to 115, stop should not decrease
        pos.update_trailing_stop(115.0)
        assert pos.highest_price == 120.0
        assert pos.stop_loss == pytest.approx(120.0 * 0.95)  # Still 114.0

    def test_bars_held(self):
        pos = Position(
            side=PositionSide.LONG,
            entry_price=100.0,
            quantity=10,
            entry_timestamp=datetime(2023, 1, 1),
            entry_bar_index=5,
        )
        assert pos.bars_held(15) == 10


class TestTrade:

    def test_winner(self):
        trade = Trade(
            entry_timestamp=datetime(2023, 1, 1),
            exit_timestamp=datetime(2023, 1, 10),
            side="long",
            entry_price=100.0,
            exit_price=110.0,
            quantity=10,
            gross_pnl=100.0,
            fees=2.0,
            net_pnl=98.0,
            return_pct=0.10,
            bars_held=9,
            exit_reason="signal",
        )
        assert trade.is_winner
        assert not trade.is_loser

    def test_loser(self):
        trade = Trade(
            entry_timestamp=datetime(2023, 1, 1),
            exit_timestamp=datetime(2023, 1, 10),
            side="long",
            entry_price=100.0,
            exit_price=90.0,
            quantity=10,
            gross_pnl=-100.0,
            fees=2.0,
            net_pnl=-102.0,
            return_pct=-0.10,
            bars_held=9,
            exit_reason="stop_loss",
        )
        assert trade.is_loser
        assert not trade.is_winner
