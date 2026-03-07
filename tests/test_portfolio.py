"""Tests for the Portfolio module."""

from datetime import datetime

import pytest

from src.core.order import Order, OrderType, OrderSide
from src.core.portfolio import Portfolio


def make_filled_buy(price: float, qty: float, fees: float) -> Order:
    order = Order(
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=qty,
        signal_price=price,
        timestamp=datetime(2023, 1, 1),
    )
    order.mark_filled(price, datetime(2023, 1, 2), fees=fees, slippage=0.0)
    return order


def make_filled_sell(price: float, qty: float, fees: float) -> Order:
    order = Order(
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=qty,
        signal_price=price,
        timestamp=datetime(2023, 1, 10),
    )
    order.mark_filled(price, datetime(2023, 1, 11), fees=fees, slippage=0.0)
    return order


class TestPortfolio:

    def test_initial_state(self):
        port = Portfolio(100_000)
        assert port.cash == 100_000
        assert not port.has_position
        assert port.total_value(100.0) == 100_000

    def test_open_position(self):
        port = Portfolio(100_000)
        buy = make_filled_buy(100.0, 100, fees=10.0)
        port.open_position(buy, bar_index=0)

        assert port.has_position
        assert port.position.quantity == 100
        assert port.position.entry_price == 100.0
        # Cash = 100000 - (100*100 + 10) = 89990
        assert port.cash == pytest.approx(89990.0)

    def test_close_position_profit(self):
        port = Portfolio(100_000)
        buy = make_filled_buy(100.0, 100, fees=10.0)
        port.open_position(buy, bar_index=0)

        sell = make_filled_sell(110.0, 100, fees=11.0)
        trade = port.close_position(sell, current_bar_index=10, exit_reason="signal")

        assert trade is not None
        assert trade.gross_pnl == pytest.approx(1000.0)  # (110-100)*100
        assert trade.fees == pytest.approx(21.0)  # entry(10) + exit(11)
        assert trade.net_pnl == pytest.approx(979.0)  # 1000 - 21
        assert trade.bars_held == 10
        assert not port.has_position

    def test_close_position_loss(self):
        port = Portfolio(100_000)
        buy = make_filled_buy(100.0, 100, fees=10.0)
        port.open_position(buy, bar_index=0)

        sell = make_filled_sell(90.0, 100, fees=9.0)
        trade = port.close_position(sell, current_bar_index=5, exit_reason="stop_loss")

        assert trade is not None
        assert trade.gross_pnl == pytest.approx(-1000.0)  # (90-100)*100
        assert trade.fees == pytest.approx(19.0)  # entry(10) + exit(9)
        assert trade.net_pnl == pytest.approx(-1019.0)  # -1000 - 19
        assert trade.exit_reason == "stop_loss"

    def test_cannot_open_two_positions(self):
        port = Portfolio(100_000)
        buy1 = make_filled_buy(100.0, 100, fees=10.0)
        port.open_position(buy1, bar_index=0)

        buy2 = make_filled_buy(105.0, 100, fees=10.5)
        port.open_position(buy2, bar_index=1)  # Should be ignored

        assert port.position.entry_price == 100.0  # First position unchanged

    def test_record_state(self):
        port = Portfolio(100_000)
        port.record_state(datetime(2023, 1, 1), 100.0)

        eq = port.get_equity_curve()
        assert len(eq) == 1
        assert eq["equity"].iloc[0] == 100_000

    def test_total_value_with_position(self):
        port = Portfolio(100_000)
        buy = make_filled_buy(100.0, 100, fees=10.0)
        port.open_position(buy, bar_index=0)

        # Cash = 89990, position = 100 * 110 = 11000
        assert port.total_value(110.0) == pytest.approx(100990.0)

    def test_reset(self):
        port = Portfolio(100_000)
        buy = make_filled_buy(100.0, 100, fees=10.0)
        port.open_position(buy, bar_index=0)
        port.reset()

        assert port.cash == 100_000
        assert not port.has_position
        assert len(port.trades) == 0

    def test_trade_log_dataframe(self):
        port = Portfolio(100_000)
        buy = make_filled_buy(100.0, 50, fees=5.0)
        port.open_position(buy, bar_index=0)

        sell = make_filled_sell(110.0, 50, fees=5.5)
        port.close_position(sell, current_bar_index=10, exit_reason="signal")

        log = port.get_trade_log()
        assert len(log) == 1
        assert "entry_price" in log.columns
        assert "net_pnl" in log.columns
        assert "exit_reason" in log.columns
