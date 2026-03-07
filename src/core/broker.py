"""
Broker module for the backtesting engine.

The Broker acts as the intermediary between strategies and the portfolio.
It handles position sizing, order creation, risk management checks,
and coordinates order execution.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from src.core.execution import ExecutionEngine
from src.core.order import Order, OrderType, OrderSide
from src.core.portfolio import Portfolio
from src.core.position import Trade
from src.utils.config import BacktestConfig, PositionSizingMethod
from src.utils.logger import setup_logger

logger = setup_logger("broker")


class Broker:
    """Coordinates order creation, sizing, execution, and portfolio updates.

    Attributes:
        config: Backtesting configuration.
        portfolio: The portfolio being managed.
        execution_engine: Handles order fill simulation.
        pending_orders: Orders waiting to be executed on the next bar.
    """

    def __init__(self, config: BacktestConfig, portfolio: Portfolio) -> None:
        self.config = config
        self.portfolio = portfolio
        self.execution_engine = ExecutionEngine(
            fee_rate=config.fee_rate,
            slippage_rate=config.slippage_rate,
        )
        self.pending_orders: list[Order] = []
        self._drawdown_killed = False

    @property
    def is_killed(self) -> bool:
        """Whether the drawdown kill switch has been triggered."""
        return self._drawdown_killed

    def submit_buy(
        self,
        signal_price: float,
        timestamp: datetime,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
        quantity: Optional[float] = None,
        reason: str = "strategy_signal",
    ) -> Optional[Order]:
        """Submit a buy order.

        If quantity is not provided, position sizing rules from config
        are applied.

        Args:
            signal_price: Price at which the signal was generated.
            timestamp: Signal bar timestamp.
            order_type: Market or limit.
            limit_price: Required for limit orders.
            quantity: Override quantity (if None, uses position sizing).
            reason: Human-readable reason for the order.

        Returns:
            The created Order, or None if rejected.
        """
        if self._drawdown_killed:
            logger.warning("Buy order rejected: drawdown kill switch active")
            return None

        if self.portfolio.has_position:
            logger.debug("Buy order rejected: already have an open position")
            return None

        # Calculate quantity if not provided
        if quantity is None:
            quantity = self._calculate_position_size(signal_price)

        if quantity <= 0:
            logger.warning("Buy order rejected: calculated quantity <= 0")
            return None

        # Check if we can afford it
        estimated_cost = signal_price * quantity * (1 + self.config.fee_rate + self.config.slippage_rate)
        if estimated_cost > self.portfolio.cash:
            # Reduce quantity to what we can afford
            affordable = self.portfolio.cash / (signal_price * (1 + self.config.fee_rate + self.config.slippage_rate))
            quantity = max(0, affordable)
            if quantity <= 0:
                logger.warning("Buy order rejected: insufficient cash")
                return None
            logger.debug(f"Adjusted quantity to {quantity:.4f} due to cash constraint")

        # Stop-loss and take-profit prices are NOT set here because
        # signal_price != actual fill_price. They are recalculated from
        # the real fill_price in process_pending_orders after the fill.
        order = Order(
            side=OrderSide.BUY,
            order_type=order_type,
            quantity=quantity,
            signal_price=signal_price,
            timestamp=timestamp,
            limit_price=limit_price,
            trailing_stop_pct=self.config.risk.trailing_stop_pct,
            reason=reason,
        )

        self.pending_orders.append(order)
        logger.debug(f"Buy order submitted: {quantity:.4f} @ ~{signal_price:.4f}")
        return order

    def submit_sell(
        self,
        signal_price: float,
        timestamp: datetime,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
        reason: str = "strategy_signal",
    ) -> Optional[Order]:
        """Submit a sell order to close the current position.

        Args:
            signal_price: Price at which the signal was generated.
            timestamp: Signal bar timestamp.
            order_type: Market or limit.
            limit_price: Required for limit orders.
            reason: Human-readable reason.

        Returns:
            The created Order, or None if rejected.
        """
        if not self.portfolio.has_position:
            logger.debug("Sell order rejected: no open position")
            return None

        quantity = self.portfolio.position.quantity

        order = Order(
            side=OrderSide.SELL,
            order_type=order_type,
            quantity=quantity,
            signal_price=signal_price,
            timestamp=timestamp,
            limit_price=limit_price,
            reason=reason,
        )

        self.pending_orders.append(order)
        logger.debug(f"Sell order submitted: {quantity:.4f} @ ~{signal_price:.4f}")
        return order

    def process_pending_orders(
        self,
        bar: pd.Series,
        bar_timestamp: datetime,
        bar_index: int,
    ) -> list[Order]:
        """Execute pending orders against the current bar.

        Processes sell orders before buy orders to free up cash.

        Args:
            bar: Current bar OHLCV data.
            bar_timestamp: Timestamp of the current bar.
            bar_index: Index of the current bar.

        Returns:
            List of orders that were filled.
        """
        filled_orders: list[Order] = []
        remaining_orders: list[Order] = []

        # Separate sells and buys — process sells first
        sell_orders = [o for o in self.pending_orders if o.is_sell]
        buy_orders = [o for o in self.pending_orders if o.is_buy]

        for order in sell_orders:
            success = self.execution_engine.execute_order(order, bar, bar_timestamp)
            if success:
                self.portfolio.close_position(order, bar_index, exit_reason=order.reason)
                filled_orders.append(order)
            else:
                remaining_orders.append(order)

        for order in buy_orders:
            success = self.execution_engine.execute_order(order, bar, bar_timestamp)
            if success:
                # Calculate stop/TP from actual fill price, not signal price
                order.stop_loss = self._get_stop_loss(order.fill_price)
                order.take_profit = self._get_take_profit(order.fill_price)
                self.portfolio.open_position(order, bar_index)
                filled_orders.append(order)
            else:
                remaining_orders.append(order)

        self.pending_orders = remaining_orders
        return filled_orders

    def check_risk_exits(
        self,
        bar: pd.Series,
        bar_timestamp: datetime,
        bar_index: int,
    ) -> Optional[Trade]:
        """Check if risk management rules trigger a position exit.

        Checks stop-loss, take-profit, trailing stop, and drawdown kill switch.
        Processes exits immediately (not queued as pending).

        Args:
            bar: Current bar OHLCV data.
            bar_timestamp: Timestamp of the current bar.
            bar_index: Index of the current bar.

        Returns:
            Trade record if position was closed, None otherwise.
        """
        if not self.portfolio.has_position:
            return None

        pos = self.portfolio.position

        # Update trailing stop
        pos.update_trailing_stop(bar["high"])

        # Check stop loss (handles gap-down)
        exit_price = pos.check_stop_loss(bar["low"], bar["open"])
        if exit_price is not None:
            return self._execute_risk_exit(
                exit_price, bar_timestamp, bar_index, "stop_loss"
            )

        # Check take profit (handles gap-up)
        exit_price = pos.check_take_profit(bar["high"], bar["open"])
        if exit_price is not None:
            return self._execute_risk_exit(
                exit_price, bar_timestamp, bar_index, "take_profit"
            )

        # Check drawdown kill switch
        if self.config.risk.max_drawdown_kill_pct is not None:
            current_value = self.portfolio.total_value(bar["close"])
            drawdown_pct = (self.portfolio.peak_value - current_value) / self.portfolio.peak_value
            if drawdown_pct >= self.config.risk.max_drawdown_kill_pct:
                logger.warning(
                    f"Drawdown kill switch triggered: {drawdown_pct:.2%} >= "
                    f"{self.config.risk.max_drawdown_kill_pct:.2%}"
                )
                self._drawdown_killed = True
                return self._execute_risk_exit(
                    bar["close"], bar_timestamp, bar_index, "drawdown_kill"
                )

        return None

    def _execute_risk_exit(
        self,
        exit_price: float,
        timestamp: datetime,
        bar_index: int,
        reason: str,
    ) -> Optional[Trade]:
        """Execute an immediate risk-management exit.

        Creates and fills a sell order at the determined exit price,
        bypassing the pending order queue.

        Args:
            exit_price: Price at which to exit.
            timestamp: Current bar timestamp.
            bar_index: Current bar index.
            reason: Exit reason.

        Returns:
            Trade record, or None if no position to close.
        """
        if not self.portfolio.has_position:
            return None

        pos = self.portfolio.position

        # Apply slippage to exit price (sells slip downward = worse fill)
        slippage = self.execution_engine._calculate_slippage(exit_price, OrderSide.SELL)
        slipped_price = exit_price + slippage
        fees = self.execution_engine.calculate_fees(slipped_price, pos.quantity)

        order = Order(
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=pos.quantity,
            signal_price=exit_price,
            timestamp=timestamp,
            reason=reason,
        )
        order.mark_filled(slipped_price, timestamp, fees, abs(slippage))

        trade = self.portfolio.close_position(order, bar_index, exit_reason=reason)

        # Cancel any pending orders to prevent accidental re-entry
        # after a risk-triggered exit (e.g., a stale buy order from
        # the previous bar reopening a position right after a stop-loss).
        cancelled = self.cancel_pending_orders()
        if cancelled > 0:
            logger.info(f"Cancelled {cancelled} pending order(s) after {reason} exit")

        return trade

    def _calculate_position_size(self, price: float) -> float:
        """Calculate position size based on the configured method.

        Args:
            price: Estimated entry price.

        Returns:
            Number of units to trade.
        """
        method = self.config.position_sizing

        if method == PositionSizingMethod.FIXED_QUANTITY:
            return self.config.fixed_quantity

        elif method == PositionSizingMethod.PERCENT_OF_EQUITY:
            available = self.portfolio.cash * self.config.position_size_pct
            max_allowed = self.portfolio.cash * self.config.risk.max_position_size_pct
            usable = min(available, max_allowed)
            # Account for fees and slippage in sizing
            adjusted_price = price * (1 + self.config.fee_rate + self.config.slippage_rate)
            return usable / adjusted_price if adjusted_price > 0 else 0

        elif method == PositionSizingMethod.RISK_BASED:
            # Risk-based: risk X% of equity per trade, based on stop distance
            equity = self.portfolio.cash
            risk_amount = equity * self.config.risk.max_risk_per_trade_pct
            stop_pct = self.config.risk.stop_loss_pct or 0.02
            stop_distance = price * stop_pct
            if stop_distance <= 0:
                return 0
            quantity = risk_amount / stop_distance
            # Cap at max position size
            max_value = equity * self.config.risk.max_position_size_pct
            max_quantity = max_value / price if price > 0 else 0
            return min(quantity, max_quantity)

        return 0

    def _get_stop_loss(self, price: float) -> Optional[float]:
        """Calculate stop-loss price from config."""
        if self.config.risk.stop_loss_pct is not None:
            return price * (1 - self.config.risk.stop_loss_pct)
        return None

    def _get_take_profit(self, price: float) -> Optional[float]:
        """Calculate take-profit price from config."""
        if self.config.risk.take_profit_pct is not None:
            return price * (1 + self.config.risk.take_profit_pct)
        return None

    def cancel_pending_orders(self) -> int:
        """Cancel all pending orders.

        Returns:
            Number of orders cancelled.
        """
        count = len(self.pending_orders)
        for order in self.pending_orders:
            order.mark_cancelled("cancelled_by_broker")
        self.pending_orders = []
        return count
