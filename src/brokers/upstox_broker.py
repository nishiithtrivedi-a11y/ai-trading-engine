"""
Upstox broker integration placeholder.

Implements the BaseBroker interface for the Upstox API.
All methods raise ``NotImplementedError`` until the
``upstox-python-sdk`` package is installed and credentials
are configured.

See: https://upstox.com/developer/api-documentation/
"""

from __future__ import annotations

from typing import Any, Optional

from src.brokers.base import BaseBroker, BrokerError, OrderResponse, OrderStatus
from src.utils.logger import setup_logger

logger = setup_logger("upstox_broker")


class UpstoxBroker(BaseBroker):
    """Upstox API broker integration.

    Requires::

        pip install upstox-python-sdk

    Usage::

        broker = UpstoxBroker(api_key="xxx", api_secret="yyy")
        broker.authenticate(access_token="zzz")
        broker.place_order("RELIANCE", "buy", 10)
    """

    def __init__(self, api_key: str, api_secret: str) -> None:
        super().__init__(api_key, api_secret)
        self._client = None  # Will hold the Upstox client instance

    def authenticate(self, access_token: str) -> bool:
        """Authenticate with Upstox.

        Raises:
            NotImplementedError: Always (placeholder).
        """
        raise NotImplementedError(
            "Upstox authentication requires the 'upstox-python-sdk' package. "
            "Install with: pip install upstox-python-sdk. "
            "Then pass your access_token from the Upstox login flow."
        )

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
    ) -> OrderResponse:
        """Place an order on Upstox.

        Raises:
            NotImplementedError: Always (placeholder).
        """
        raise NotImplementedError(
            "Upstox order placement requires upstox-python-sdk. "
            "See https://upstox.com/developer/api-documentation/ for setup."
        )

    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an order on Upstox.

        Raises:
            NotImplementedError: Always (placeholder).
        """
        raise NotImplementedError("Upstox order cancellation not yet implemented")

    def get_order_status(self, order_id: str) -> OrderResponse:
        """Get order status from Upstox.

        Raises:
            NotImplementedError: Always (placeholder).
        """
        raise NotImplementedError("Upstox order status not yet implemented")

    def get_orders(self) -> list[OrderResponse]:
        """Get all orders from Upstox.

        Raises:
            NotImplementedError: Always (placeholder).
        """
        raise NotImplementedError("Upstox get_orders not yet implemented")

    def get_positions(self) -> list[dict[str, Any]]:
        """Get positions from Upstox.

        Raises:
            NotImplementedError: Always (placeholder).
        """
        raise NotImplementedError("Upstox positions not yet implemented")

    def get_holdings(self) -> list[dict[str, Any]]:
        """Get holdings from Upstox.

        Raises:
            NotImplementedError: Always (placeholder).
        """
        raise NotImplementedError("Upstox holdings not yet implemented")

    def get_account_summary(self) -> dict[str, Any]:
        """Get account summary from Upstox.

        Raises:
            NotImplementedError: Always (placeholder).
        """
        raise NotImplementedError("Upstox account summary not yet implemented")
