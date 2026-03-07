"""
Position tracking for the backtesting engine.

Manages open positions, average entry price, unrealized PnL,
and stop/take-profit levels.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd


class PositionSide:
    LONG = "long"
    SHORT = "short"  # Placeholder for future short support


@dataclass
class Position:
    """Represents an open trading position.

    Attributes:
        side: Long or short.
        entry_price: Average entry price.
        quantity: Number of units held.
        entry_timestamp: When the position was opened.
        stop_loss: Current stop-loss price.
        take_profit: Current take-profit price.
        trailing_stop_pct: Trailing stop as fraction of peak price.
        highest_price: Highest price seen since entry (for trailing stop).
        entry_bar_index: Index of the bar where entry occurred.
    """
    side: str
    entry_price: float
    quantity: float
    entry_timestamp: datetime
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    highest_price: Optional[float] = None
    entry_bar_index: int = 0
    entry_fees: float = 0.0

    def __post_init__(self) -> None:
        if self.highest_price is None:
            self.highest_price = self.entry_price

    @property
    def is_long(self) -> bool:
        return self.side == PositionSide.LONG

    def market_value(self, current_price: float) -> float:
        """Current market value of the position."""
        return self.quantity * current_price

    def unrealized_pnl(self, current_price: float) -> float:
        """Unrealized profit/loss at current price."""
        if self.is_long:
            return self.quantity * (current_price - self.entry_price)
        return self.quantity * (self.entry_price - current_price)

    def unrealized_pnl_pct(self, current_price: float) -> float:
        """Unrealized PnL as a percentage of entry value."""
        entry_value = self.quantity * self.entry_price
        if entry_value == 0:
            return 0.0
        return self.unrealized_pnl(current_price) / entry_value

    def update_trailing_stop(self, current_high: float) -> Optional[float]:
        """Update trailing stop based on new high price.

        Args:
            current_high: The high price of the current bar.

        Returns:
            Updated trailing stop price, or None if no trailing stop is set.
        """
        if self.trailing_stop_pct is None:
            return None

        if self.highest_price is None or current_high > self.highest_price:
            self.highest_price = current_high

        trailing_stop_price = self.highest_price * (1 - self.trailing_stop_pct)

        # Update stop_loss to trailing stop if it's higher than current stop
        if self.stop_loss is None or trailing_stop_price > self.stop_loss:
            self.stop_loss = trailing_stop_price

        return self.stop_loss

    def check_stop_loss(self, current_low: float, current_open: float) -> Optional[float]:
        """Check if stop loss is triggered.

        Handles gap-down scenarios: if the bar opens below the stop,
        the fill price is the open (not the stop level).

        Args:
            current_low: Low price of current bar.
            current_open: Open price of current bar.

        Returns:
            Exit price if stop is triggered, None otherwise.
        """
        if self.stop_loss is None:
            return None

        if self.is_long:
            # Gap down: open is already below stop
            if current_open <= self.stop_loss:
                return current_open
            # Intra-bar stop hit
            if current_low <= self.stop_loss:
                return self.stop_loss
        return None

    def check_take_profit(self, current_high: float, current_open: float) -> Optional[float]:
        """Check if take profit is triggered.

        Handles gap-up scenarios similarly to stop loss.

        Args:
            current_high: High price of current bar.
            current_open: Open price of current bar.

        Returns:
            Exit price if take profit is triggered, None otherwise.
        """
        if self.take_profit is None:
            return None

        if self.is_long:
            # Gap up: open is already above take profit
            if current_open >= self.take_profit:
                return current_open
            # Intra-bar take profit hit
            if current_high >= self.take_profit:
                return self.take_profit
        return None

    def bars_held(self, current_bar_index: int) -> int:
        """Number of bars the position has been held."""
        return current_bar_index - self.entry_bar_index

    def holding_minutes(self, exit_timestamp: datetime) -> float:
        """Return holding duration in minutes."""
        entry_ts = pd.Timestamp(self.entry_timestamp)
        exit_ts = pd.Timestamp(exit_timestamp)
        delta = exit_ts - entry_ts
        return max(delta.total_seconds() / 60.0, 0.0)


@dataclass
class Trade:
    """A completed (closed) trade record.

    Created when a position is fully closed.
    """
    entry_timestamp: datetime
    exit_timestamp: datetime
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    fees: float
    net_pnl: float
    return_pct: float
    bars_held: int
    exit_reason: str
    holding_minutes: float = 0.0

    @property
    def is_winner(self) -> bool:
        return self.net_pnl > 0

    @property
    def is_loser(self) -> bool:
        return self.net_pnl < 0