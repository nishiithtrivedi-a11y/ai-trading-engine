"""
Portfolio management for the backtesting engine.

Tracks cash, equity, positions, trade history, and generates
the equity curve and drawdown series.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd

from src.core.order import Order
from src.core.position import Position, PositionSide, Trade
from src.utils.logger import setup_logger

logger = setup_logger("portfolio")


@dataclass
class PortfolioState:
    """Snapshot of portfolio state at a point in time."""
    timestamp: datetime
    cash: float
    equity: float
    total_value: float
    unrealized_pnl: float
    realized_pnl: float
    drawdown: float
    drawdown_pct: float


class Portfolio:
    """Manages portfolio state, position lifecycle, and trade recording.

    Supports a single active position at a time (designed to be extended
    for multi-position support).

    Attributes:
        initial_capital: Starting cash amount.
        cash: Current cash balance.
        position: Current open position (or None).
        trades: List of completed trades.
        equity_curve: Time series of portfolio values.
    """

    def __init__(self, initial_capital: float) -> None:
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.position: Optional[Position] = None
        self.trades: list[Trade] = []

        # Running totals
        self.realized_pnl: float = 0.0
        self.total_fees: float = 0.0
        self.peak_value: float = initial_capital

        # Time series records
        self._equity_records: list[dict] = []

    @property
    def has_position(self) -> bool:
        """Whether there is an open position."""
        return self.position is not None

    def total_value(self, current_price: float) -> float:
        """Total portfolio value (cash + position market value)."""
        if self.position is not None:
            return self.cash + self.position.market_value(current_price)
        return self.cash

    def unrealized_pnl(self, current_price: float) -> float:
        """Current unrealized PnL."""
        if self.position is not None:
            return self.position.unrealized_pnl(current_price)
        return 0.0

    def open_position(
        self,
        order: Order,
        bar_index: int,
    ) -> None:
        """Open a new position from a filled buy order.

        Args:
            order: The filled buy order.
            bar_index: Index of the bar where entry occurs.
        """
        if self.position is not None:
            logger.warning("Cannot open position: already have an open position")
            return

        if not order.is_filled:
            logger.error("Cannot open position from unfilled order")
            return

        cost = order.fill_price * order.quantity + order.fees
        if cost > self.cash:
            logger.warning(
                f"Insufficient cash for position: need {cost:.2f}, have {self.cash:.2f}"
            )
            return

        self.cash -= cost
        self.total_fees += order.fees

        self.position = Position(
            side=PositionSide.LONG if order.is_buy else PositionSide.SHORT,
            entry_price=order.fill_price,
            quantity=order.quantity,
            entry_timestamp=order.fill_timestamp,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            trailing_stop_pct=order.trailing_stop_pct,
            entry_bar_index=bar_index,
            entry_fees=order.fees,
        )

        logger.debug(
            f"Opened {self.position.side} position: "
            f"{order.quantity:.4f} @ {order.fill_price:.4f} "
            f"(cost={cost:.2f}, fees={order.fees:.4f})"
        )

    def close_position(
        self,
        order: Order,
        current_bar_index: int,
        exit_reason: str = "signal",
    ) -> Optional[Trade]:
        """Close the current position from a filled sell order.

        Args:
            order: The filled sell order.
            current_bar_index: Index of the exit bar.
            exit_reason: Why the position was closed.

        Returns:
            The completed Trade record, or None if no position exists.
        """
        if self.position is None:
            logger.warning("Cannot close position: no open position")
            return None

        if not order.is_filled:
            logger.error("Cannot close position from unfilled order")
            return None

        pos = self.position

        # Calculate PnL
        if pos.is_long:
            gross_pnl = (order.fill_price - pos.entry_price) * pos.quantity
        else:
            gross_pnl = (pos.entry_price - order.fill_price) * pos.quantity

        # Fee accounting: entry fees were already deducted from cash at open.
        # Exit fees are deducted now. Both are recorded on the Trade for
        # accurate per-trade profitability.
        exit_fees = order.fees
        total_trade_fees = pos.entry_fees + exit_fees
        self.total_fees += exit_fees

        net_pnl = gross_pnl - total_trade_fees
        entry_value = pos.entry_price * pos.quantity
        return_pct = net_pnl / entry_value if entry_value > 0 else 0.0

        # Credit cash: sale proceeds minus exit fees
        proceeds = order.fill_price * pos.quantity - exit_fees
        self.cash += proceeds

        self.realized_pnl += net_pnl

        # Record trade
        trade = Trade(
            entry_timestamp=pos.entry_timestamp,
            exit_timestamp=order.fill_timestamp,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=order.fill_price,
            quantity=pos.quantity,
            gross_pnl=gross_pnl,
            fees=total_trade_fees,
            net_pnl=net_pnl,
            return_pct=return_pct,
            bars_held=pos.bars_held(current_bar_index),
            exit_reason=exit_reason,
            holding_minutes=pos.holding_minutes(order.fill_timestamp),
        )

        self.trades.append(trade)
        self.position = None

        logger.debug(
            f"Closed position: {pos.side} {pos.quantity:.4f} "
            f"@ {order.fill_price:.4f} | PnL={net_pnl:.2f} ({return_pct:.2%}) "
            f"| reason={exit_reason}"
        )

        return trade

    def record_state(self, timestamp: datetime, current_price: float) -> None:
        """Record the current portfolio state for the equity curve.

        Called once per bar after all processing.

        Args:
            timestamp: Current bar timestamp.
            current_price: Current close price for position valuation.
        """
        tv = self.total_value(current_price)
        unrealized = self.unrealized_pnl(current_price)

        # Update peak
        if tv > self.peak_value:
            self.peak_value = tv

        # Calculate drawdown
        drawdown = self.peak_value - tv
        drawdown_pct = drawdown / self.peak_value if self.peak_value > 0 else 0.0

        self._equity_records.append({
            "timestamp": timestamp,
            "cash": self.cash,
            "equity": tv,
            "unrealized_pnl": unrealized,
            "realized_pnl": self.realized_pnl,
            "drawdown": drawdown,
            "drawdown_pct": drawdown_pct,
        })

    def get_equity_curve(self) -> pd.DataFrame:
        """Get the equity curve as a DataFrame."""
        if not self._equity_records:
            return pd.DataFrame()
        df = pd.DataFrame(self._equity_records)
        df.set_index("timestamp", inplace=True)
        return df

    def get_trade_log(self) -> pd.DataFrame:
        """Get the trade log as a DataFrame."""
        if not self.trades:
            return pd.DataFrame()

        records = []
        for t in self.trades:
            records.append({
                "entry_timestamp": t.entry_timestamp,
                "exit_timestamp": t.exit_timestamp,
                "side": t.side,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "gross_pnl": t.gross_pnl,
                "net_pnl": t.net_pnl,
                "fees": t.fees,
                "return_pct": t.return_pct,
                "bars_held": t.bars_held,
                "holding_minutes": t.holding_minutes,
                "exit_reason": t.exit_reason,
            })

        return pd.DataFrame(records)

    def reset(self) -> None:
        """Reset the portfolio to initial state."""
        self.cash = self.initial_capital
        self.position = None
        self.trades = []
        self.realized_pnl = 0.0
        self.total_fees = 0.0
        self.peak_value = self.initial_capital
        self._equity_records = []