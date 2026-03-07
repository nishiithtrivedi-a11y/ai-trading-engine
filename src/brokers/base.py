"""
Abstract base class for live broker integrations.

Defines a uniform interface that all broker implementations
(Zerodha, Upstox, etc.) must follow. This is separate from the
backtesting ``Broker`` in ``src/core/broker.py`` — that class
simulates execution, while these classes will connect to real
broker APIs.

All methods raise ``NotImplementedError`` by default, allowing
incremental implementation as broker SDKs are integrated.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from src.utils.logger import setup_logger

logger = setup_logger("broker_base")


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

class OrderStatus(str, Enum):
    """Standard order status across all brokers."""
    PENDING = "pending"
    OPEN = "open"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


class BrokerError(Exception):
    """Base exception for broker-related errors."""
    pass


@dataclass
class OrderResponse:
    """Standardized order response returned by all broker implementations.

    Provides a uniform shape regardless of the underlying broker API.
    """
    order_id: str
    status: OrderStatus
    symbol: str
    side: str  # "buy" or "sell"
    quantity: float
    price: Optional[float] = None
    order_type: str = "market"  # "market", "limit", "sl", "sl-m"
    timestamp: Optional[datetime] = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "status": self.status.value,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "order_type": self.order_type,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


# ---------------------------------------------------------------------------
# BaseBroker ABC
# ---------------------------------------------------------------------------

class BaseBroker(ABC):
    """Abstract base class for live broker integrations.

    Subclasses should implement each method to connect to the
    broker's SDK / REST API. All methods raise ``NotImplementedError``
    until the concrete implementation is provided.

    Typical lifecycle::

        broker = ZerodhaBroker(api_key, api_secret)
        broker.authenticate(access_token)
        positions = broker.get_positions()
        resp = broker.place_order("RELIANCE", "buy", 10)
        broker.cancel_order(resp.order_id)
        summary = broker.get_account_summary()
    """

    def __init__(self, api_key: str, api_secret: str) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self._authenticated: bool = False

    @property
    def is_authenticated(self) -> bool:
        """Whether the broker session is authenticated."""
        return self._authenticated

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    @abstractmethod
    def authenticate(self, access_token: str) -> bool:
        """Authenticate with the broker.

        Args:
            access_token: Session/access token from the broker's
                login flow (typically OAuth2).

        Returns:
            True if authentication succeeded.

        Raises:
            BrokerError: On authentication failure.
        """
        ...

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
    ) -> OrderResponse:
        """Place a new order.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE", "NIFTY 50").
            side: "buy" or "sell".
            quantity: Number of shares/lots.
            order_type: "market", "limit", "sl", or "sl-m".
            price: Limit price (required for limit/sl orders).
            trigger_price: Stop-loss trigger price (for sl/sl-m orders).

        Returns:
            OrderResponse with order details and status.

        Raises:
            BrokerError: If order placement fails.
        """
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel a pending order.

        Args:
            order_id: Broker-assigned order identifier.

        Returns:
            Updated OrderResponse.

        Raises:
            BrokerError: If cancellation fails.
        """
        ...

    @abstractmethod
    def get_order_status(self, order_id: str) -> OrderResponse:
        """Get the current status of an order.

        Args:
            order_id: Broker-assigned order identifier.

        Returns:
            OrderResponse with current status.
        """
        ...

    @abstractmethod
    def get_orders(self) -> list[OrderResponse]:
        """Get all orders for the current session.

        Returns:
            List of OrderResponse objects.
        """
        ...

    # ------------------------------------------------------------------
    # Position and account queries
    # ------------------------------------------------------------------

    @abstractmethod
    def get_positions(self) -> list[dict[str, Any]]:
        """Get current open positions.

        Returns:
            List of position dicts with at least:
            ``symbol``, ``quantity``, ``average_price``, ``pnl``.
        """
        ...

    @abstractmethod
    def get_holdings(self) -> list[dict[str, Any]]:
        """Get long-term holdings (delivery positions).

        Returns:
            List of holding dicts.
        """
        ...

    @abstractmethod
    def get_account_summary(self) -> dict[str, Any]:
        """Get account-level information.

        Returns:
            Dict with at least: ``available_cash``, ``used_margin``,
            ``total_equity``.
        """
        ...
