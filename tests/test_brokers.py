"""Tests for broker integration placeholders (Step 11)."""

from datetime import datetime

import pytest

from src.brokers.base import BaseBroker, BrokerError, OrderResponse, OrderStatus
from src.brokers.zerodha_broker import ZerodhaBroker
from src.brokers.upstox_broker import UpstoxBroker


# ---------------------------------------------------------------------------
# Tests — OrderResponse and OrderStatus
# ---------------------------------------------------------------------------

class TestOrderResponseAndStatus:

    def test_order_status_values(self):
        assert OrderStatus.PENDING.value == "pending"
        assert OrderStatus.COMPLETE.value == "complete"
        assert OrderStatus.CANCELLED.value == "cancelled"
        assert OrderStatus.REJECTED.value == "rejected"

    def test_order_response_to_dict(self):
        resp = OrderResponse(
            order_id="ORD123",
            status=OrderStatus.COMPLETE,
            symbol="RELIANCE",
            side="buy",
            quantity=10,
            price=2500.0,
        )
        d = resp.to_dict()
        assert d["order_id"] == "ORD123"
        assert d["status"] == "complete"
        assert d["symbol"] == "RELIANCE"
        assert d["side"] == "buy"
        assert d["quantity"] == 10
        assert d["price"] == 2500.0

    def test_order_response_defaults(self):
        resp = OrderResponse(
            order_id="ORD1",
            status=OrderStatus.PENDING,
            symbol="TCS",
            side="sell",
            quantity=5,
        )
        assert resp.order_type == "market"
        assert resp.price is None
        assert resp.timestamp is None
        assert resp.raw == {}

    def test_broker_error_is_exception(self):
        with pytest.raises(BrokerError):
            raise BrokerError("Test error")


# ---------------------------------------------------------------------------
# Tests — ZerodhaBroker stub
# ---------------------------------------------------------------------------

class TestZerodhaBroker:
    """Tests for the implemented Zerodha broker integration.

    All methods now raise BrokerError (not NotImplementedError) because
    the implementation is real — it just requires valid authentication.
    """

    def _make_broker(self) -> ZerodhaBroker:
        return ZerodhaBroker(api_key="test_key", api_secret="test_secret")

    def test_initial_state(self):
        broker = self._make_broker()
        assert broker.api_key == "test_key"
        assert broker.api_secret == "test_secret"
        assert broker.is_authenticated is False

    def test_custom_order_defaults_are_configurable(self):
        broker = ZerodhaBroker(
            api_key="test_key",
            api_secret="test_secret",
            default_exchange="BSE",
            default_product="MIS",
            default_variety="AMO",
        )
        assert broker.default_exchange == "BSE"
        assert broker.default_product == "MIS"
        assert broker.default_variety == "AMO"

    def test_broker_timestamp_prefers_payload_timestamp(self):
        payload = {"order_timestamp": "2026-03-16T09:30:00+05:30"}
        ts = ZerodhaBroker._broker_timestamp(payload)
        assert isinstance(ts, datetime)
        assert ts.year == 2026

    def test_authenticate_with_bad_credentials_raises_broker_error(self):
        broker = self._make_broker()
        with pytest.raises(BrokerError, match="authentication failed"):
            broker.authenticate("invalid_token")

    def test_place_order_requires_auth(self):
        broker = self._make_broker()
        with pytest.raises(BrokerError, match="Not authenticated"):
            broker.place_order("RELIANCE", "buy", 10)

    def test_cancel_order_requires_auth(self):
        broker = self._make_broker()
        with pytest.raises(BrokerError, match="Not authenticated"):
            broker.cancel_order("ORD123")

    def test_get_order_status_requires_auth(self):
        broker = self._make_broker()
        with pytest.raises(BrokerError, match="Not authenticated"):
            broker.get_order_status("ORD123")

    def test_get_orders_requires_auth(self):
        broker = self._make_broker()
        with pytest.raises(BrokerError, match="Not authenticated"):
            broker.get_orders()

    def test_get_positions_requires_auth(self):
        broker = self._make_broker()
        with pytest.raises(BrokerError, match="Not authenticated"):
            broker.get_positions()

    def test_get_holdings_requires_auth(self):
        broker = self._make_broker()
        with pytest.raises(BrokerError, match="Not authenticated"):
            broker.get_holdings()

    def test_get_account_summary_requires_auth(self):
        broker = self._make_broker()
        with pytest.raises(BrokerError, match="Not authenticated"):
            broker.get_account_summary()

    def test_place_order_blocked_when_not_live_even_if_authenticated(self):
        broker = self._make_broker()
        broker._authenticated = True

        class FakeKite:
            TRANSACTION_TYPE_BUY = "BUY"
            TRANSACTION_TYPE_SELL = "SELL"

            @staticmethod
            def place_order(**_kwargs):
                return "OID-1"

        broker._kite = FakeKite()

        with pytest.raises(BrokerError, match="blocked"):
            broker.place_order("RELIANCE", "buy", 10)

    def test_place_order_allowed_when_explicit_live_enabled(self):
        broker = ZerodhaBroker(
            api_key="test_key",
            api_secret="test_secret",
            execution_mode="live",
            enable_live_execution=True,
        )
        broker._authenticated = True

        class FakeKite:
            TRANSACTION_TYPE_BUY = "BUY"
            TRANSACTION_TYPE_SELL = "SELL"

            @staticmethod
            def place_order(**_kwargs):
                return "OID-LIVE-1"

        broker._kite = FakeKite()
        response = broker.place_order("RELIANCE", "buy", 1)
        assert response.order_id == "OID-LIVE-1"


# ---------------------------------------------------------------------------
# Tests — UpstoxBroker stub
# ---------------------------------------------------------------------------

class TestUpstoxBroker:

    def _make_broker(self) -> UpstoxBroker:
        return UpstoxBroker(api_key="upstox_key", api_secret="upstox_secret")

    def test_initial_state(self):
        broker = self._make_broker()
        assert broker.api_key == "upstox_key"
        assert broker.is_authenticated is False

    def test_authenticate_raises(self):
        broker = self._make_broker()
        with pytest.raises(NotImplementedError, match="upstox-python-sdk"):
            broker.authenticate("token")

    def test_place_order_raises(self):
        broker = self._make_broker()
        with pytest.raises(NotImplementedError):
            broker.place_order("TCS", "sell", 5)

    def test_cancel_order_raises(self):
        broker = self._make_broker()
        with pytest.raises(NotImplementedError):
            broker.cancel_order("ORD456")

    def test_get_order_status_raises(self):
        broker = self._make_broker()
        with pytest.raises(NotImplementedError):
            broker.get_order_status("ORD456")

    def test_get_orders_raises(self):
        broker = self._make_broker()
        with pytest.raises(NotImplementedError):
            broker.get_orders()

    def test_get_positions_raises(self):
        broker = self._make_broker()
        with pytest.raises(NotImplementedError):
            broker.get_positions()

    def test_get_holdings_raises(self):
        broker = self._make_broker()
        with pytest.raises(NotImplementedError):
            broker.get_holdings()

    def test_get_account_summary_raises(self):
        broker = self._make_broker()
        with pytest.raises(NotImplementedError):
            broker.get_account_summary()


# ---------------------------------------------------------------------------
# Tests — BaseBroker is ABC (cannot be instantiated)
# ---------------------------------------------------------------------------

class TestBaseBrokerABC:

    def test_cannot_instantiate_directly(self):
        """BaseBroker is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            BaseBroker(api_key="k", api_secret="s")
