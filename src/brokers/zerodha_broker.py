"""
Zerodha (KiteConnect) broker integration.

Implements the BaseBroker interface for Zerodha's KiteConnect API.
Supports authentication, order placement, position/holdings queries,
and account summary.

**Safety:** Order placement is implemented but should only be used
after thorough paper-trading validation. The engine does NOT enable
live trading by default.

See: https://kite.trade/docs/connect/v3/
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from src.brokers.base import BaseBroker, BrokerError, OrderResponse, OrderStatus
from src.utils.logger import setup_logger

logger = setup_logger("zerodha_broker")

# Map engine order types to Kite order type constants
_ORDER_TYPE_MAP = {
    "market": "MARKET",
    "limit": "LIMIT",
    "sl": "SL",
    "sl-m": "SL-M",
}


class ZerodhaBroker(BaseBroker):
    """Zerodha KiteConnect broker integration.

    Requires::

        pip install kiteconnect

    Usage::

        broker = ZerodhaBroker(api_key="xxx", api_secret="yyy")
        broker.authenticate(access_token="zzz")
        profile = broker.get_account_summary()
        positions = broker.get_positions()
        resp = broker.place_order("RELIANCE", "buy", 10)
    """

    def __init__(self, api_key: str, api_secret: str) -> None:
        super().__init__(api_key, api_secret)
        self._kite = None  # KiteConnect instance

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self, access_token: str) -> bool:
        """Authenticate with Zerodha KiteConnect.

        Creates a KiteConnect client, sets the access token, and
        validates by calling ``kite.profile()``.

        Args:
            access_token: Session token from the Kite login flow.

        Returns:
            True if authentication succeeded.

        Raises:
            BrokerError: On authentication failure.
        """
        try:
            from kiteconnect import KiteConnect
        except ImportError:
            raise BrokerError(
                "kiteconnect package is not installed. "
                "Install with: pip install kiteconnect"
            )

        try:
            kite = KiteConnect(api_key=self.api_key)
            kite.set_access_token(access_token)

            # Validate by fetching profile
            profile = kite.profile()
            self._kite = kite
            self._authenticated = True

            logger.info(
                f"Authenticated as {profile.get('user_name', 'unknown')} "
                f"(user_id={profile.get('user_id')})"
            )
            return True

        except Exception as exc:
            self._authenticated = False
            raise BrokerError(f"Zerodha authentication failed: {exc}") from exc

    def _require_auth(self) -> None:
        """Raise BrokerError if not authenticated."""
        if not self._authenticated or self._kite is None:
            raise BrokerError(
                "Not authenticated. Call broker.authenticate(access_token) first."
            )

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
    ) -> OrderResponse:
        """Place an order on Zerodha.

        Args:
            symbol: NSE trading symbol (e.g., "RELIANCE").
            side: "buy" or "sell".
            quantity: Number of shares.
            order_type: "market", "limit", "sl", or "sl-m".
            price: Limit price (for limit/sl orders).
            trigger_price: Trigger price (for sl/sl-m orders).

        Returns:
            OrderResponse with order details.

        Raises:
            BrokerError: If order placement fails.
        """
        self._require_auth()

        kite_order_type = _ORDER_TYPE_MAP.get(
            order_type.lower(), "MARKET"
        )
        kite_side = (
            self._kite.TRANSACTION_TYPE_BUY
            if side.lower() == "buy"
            else self._kite.TRANSACTION_TYPE_SELL
        )

        order_params = {
            "tradingsymbol": symbol.upper(),
            "exchange": self._kite.EXCHANGE_NSE,
            "transaction_type": kite_side,
            "quantity": int(quantity),
            "order_type": kite_order_type,
            "product": self._kite.PRODUCT_CNC,  # delivery
            "variety": self._kite.VARIETY_REGULAR,
        }

        if price is not None:
            order_params["price"] = price
        if trigger_price is not None:
            order_params["trigger_price"] = trigger_price

        try:
            order_id = self._kite.place_order(**order_params)
            logger.info(
                f"Order placed: {side} {quantity} {symbol} "
                f"({order_type}) -> order_id={order_id}"
            )
            return OrderResponse(
                order_id=str(order_id),
                status=OrderStatus.PENDING,
                symbol=symbol.upper(),
                side=side.lower(),
                quantity=float(quantity),
                price=price,
                order_type=order_type,
                timestamp=datetime.now(),
            )
        except Exception as exc:
            raise BrokerError(f"Order placement failed: {exc}") from exc

    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel a pending order on Zerodha.

        Args:
            order_id: Kite order ID.

        Returns:
            Updated OrderResponse.

        Raises:
            BrokerError: If cancellation fails.
        """
        self._require_auth()
        try:
            self._kite.cancel_order(
                variety=self._kite.VARIETY_REGULAR,
                order_id=order_id,
            )
            logger.info(f"Order cancelled: {order_id}")
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.CANCELLED,
                symbol="",
                side="",
                quantity=0,
                timestamp=datetime.now(),
            )
        except Exception as exc:
            raise BrokerError(f"Cancel failed: {exc}") from exc

    def get_order_status(self, order_id: str) -> OrderResponse:
        """Get the current status of an order.

        Args:
            order_id: Kite order ID.

        Returns:
            OrderResponse with current status.
        """
        self._require_auth()
        try:
            history = self._kite.order_history(order_id)
            latest = history[-1] if history else {}

            status_map = {
                "COMPLETE": OrderStatus.COMPLETE,
                "CANCELLED": OrderStatus.CANCELLED,
                "REJECTED": OrderStatus.REJECTED,
                "OPEN": OrderStatus.OPEN,
                "PENDING": OrderStatus.PENDING,
            }
            kite_status = latest.get("status", "PENDING")

            return OrderResponse(
                order_id=order_id,
                status=status_map.get(kite_status, OrderStatus.PENDING),
                symbol=latest.get("tradingsymbol", ""),
                side=latest.get("transaction_type", "").lower(),
                quantity=float(latest.get("quantity", 0)),
                price=latest.get("average_price"),
                order_type=latest.get("order_type", "market").lower(),
                timestamp=datetime.now(),
                raw=latest,
            )
        except Exception as exc:
            raise BrokerError(f"Order status lookup failed: {exc}") from exc

    def get_orders(self) -> list[OrderResponse]:
        """Get all orders for the current trading session.

        Returns:
            List of OrderResponse objects.
        """
        self._require_auth()
        try:
            orders = self._kite.orders()
            results = []
            status_map = {
                "COMPLETE": OrderStatus.COMPLETE,
                "CANCELLED": OrderStatus.CANCELLED,
                "REJECTED": OrderStatus.REJECTED,
                "OPEN": OrderStatus.OPEN,
                "PENDING": OrderStatus.PENDING,
            }
            for o in orders:
                kite_status = o.get("status", "PENDING")
                results.append(
                    OrderResponse(
                        order_id=str(o.get("order_id", "")),
                        status=status_map.get(kite_status, OrderStatus.PENDING),
                        symbol=o.get("tradingsymbol", ""),
                        side=o.get("transaction_type", "").lower(),
                        quantity=float(o.get("quantity", 0)),
                        price=o.get("average_price"),
                        order_type=o.get("order_type", "").lower(),
                        raw=o,
                    )
                )
            return results
        except Exception as exc:
            raise BrokerError(f"Failed to fetch orders: {exc}") from exc

    # ------------------------------------------------------------------
    # Position and account queries
    # ------------------------------------------------------------------

    def get_positions(self) -> list[dict[str, Any]]:
        """Get current open positions from Zerodha.

        Returns:
            List of position dicts with ``symbol``, ``quantity``,
            ``average_price``, ``pnl``, ``product``.
        """
        self._require_auth()
        try:
            positions = self._kite.positions()
            results = []
            for category in ("net", "day"):
                for pos in positions.get(category, []):
                    results.append(
                        {
                            "symbol": pos.get("tradingsymbol", ""),
                            "exchange": pos.get("exchange", ""),
                            "quantity": pos.get("quantity", 0),
                            "average_price": pos.get("average_price", 0),
                            "pnl": pos.get("pnl", 0),
                            "product": pos.get("product", ""),
                            "category": category,
                        }
                    )
            return results
        except Exception as exc:
            raise BrokerError(f"Failed to fetch positions: {exc}") from exc

    def get_holdings(self) -> list[dict[str, Any]]:
        """Get long-term holdings (delivery positions) from Zerodha.

        Returns:
            List of holding dicts.
        """
        self._require_auth()
        try:
            holdings = self._kite.holdings()
            return [
                {
                    "symbol": h.get("tradingsymbol", ""),
                    "exchange": h.get("exchange", ""),
                    "quantity": h.get("quantity", 0),
                    "average_price": h.get("average_price", 0),
                    "last_price": h.get("last_price", 0),
                    "pnl": h.get("pnl", 0),
                    "isin": h.get("isin", ""),
                }
                for h in holdings
            ]
        except Exception as exc:
            raise BrokerError(f"Failed to fetch holdings: {exc}") from exc

    def get_account_summary(self) -> dict[str, Any]:
        """Get account-level information from Zerodha.

        Combines profile and margin data.

        Returns:
            Dict with ``user_name``, ``user_id``, ``email``,
            ``available_cash``, ``used_margin``, ``total_equity``.
        """
        self._require_auth()
        try:
            profile = self._kite.profile()
            margins = self._kite.margins()

            equity_margin = margins.get("equity", {})
            available = equity_margin.get("available", {})
            utilised = equity_margin.get("utilised", {})

            return {
                "user_name": profile.get("user_name", ""),
                "user_id": profile.get("user_id", ""),
                "email": profile.get("email", ""),
                "broker": profile.get("broker", ""),
                "available_cash": available.get("live_balance", 0),
                "used_margin": utilised.get("debits", 0),
                "total_equity": equity_margin.get("net", 0),
            }
        except Exception as exc:
            raise BrokerError(f"Failed to fetch account summary: {exc}") from exc
