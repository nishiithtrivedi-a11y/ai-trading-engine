"""
Order domain objects for the backtesting engine.

Defines order types, sides, and the Order dataclass used throughout
the execution pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class OrderType(str, Enum):
    """Supported order types."""
    MARKET = "market"
    LIMIT = "limit"


class OrderSide(str, Enum):
    """Order direction."""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    """Lifecycle status of an order."""
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    """Represents a trading order.

    Attributes:
        side: Buy or sell.
        order_type: Market or limit.
        quantity: Number of units to trade.
        signal_price: Price at which the signal was generated.
        timestamp: When the order was created (signal bar timestamp).
        limit_price: Limit price for limit orders.
        stop_loss: Optional stop-loss price.
        take_profit: Optional take-profit price.
        trailing_stop_pct: Optional trailing stop percentage.
        status: Current order status.
        fill_price: Price at which the order was filled.
        fill_timestamp: When the order was filled.
        fees: Fees charged on the fill.
        slippage: Slippage applied to the fill.
        reason: Human-readable reason for the order.
    """
    side: OrderSide
    order_type: OrderType
    quantity: float
    signal_price: float
    timestamp: datetime

    # Limit order specific
    limit_price: Optional[float] = None

    # Risk management attached to order
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop_pct: Optional[float] = None

    # Fill information (populated after execution)
    status: OrderStatus = OrderStatus.PENDING
    fill_price: Optional[float] = None
    fill_timestamp: Optional[datetime] = None
    fees: float = 0.0
    slippage: float = 0.0

    # Metadata
    reason: str = ""

    def mark_filled(self, fill_price: float, fill_timestamp: datetime, fees: float, slippage: float) -> None:
        """Mark this order as filled with execution details."""
        self.status = OrderStatus.FILLED
        self.fill_price = fill_price
        self.fill_timestamp = fill_timestamp
        self.fees = fees
        self.slippage = slippage

    def mark_cancelled(self, reason: str = "") -> None:
        """Mark this order as cancelled."""
        self.status = OrderStatus.CANCELLED
        self.reason = reason if reason else self.reason

    def mark_rejected(self, reason: str = "") -> None:
        """Mark this order as rejected."""
        self.status = OrderStatus.REJECTED
        self.reason = reason if reason else self.reason

    @property
    def is_buy(self) -> bool:
        return self.side == OrderSide.BUY

    @property
    def is_sell(self) -> bool:
        return self.side == OrderSide.SELL

    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED
