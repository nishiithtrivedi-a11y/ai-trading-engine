"""
Order execution simulation for the backtesting engine.

Handles fill price calculation including slippage, fee computation,
and limit order fill logic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from src.core.order import Order, OrderType, OrderSide, OrderStatus
from src.utils.logger import setup_logger

logger = setup_logger("execution")


class ExecutionEngine:
    """Simulates order execution with realistic market mechanics.

    Models slippage and fees. Limit orders fill only if the bar's
    price range includes the limit price.

    Attributes:
        fee_rate: Fee as a fraction of trade value.
        slippage_rate: Slippage as a fraction of the execution price.
    """

    def __init__(self, fee_rate: float = 0.001, slippage_rate: float = 0.0005) -> None:
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate

    def calculate_fill_price(self, order: Order, bar: pd.Series) -> Optional[float]:
        """Determine the fill price for an order given a bar's OHLCV data.

        For market orders:
            - Fills at the bar's open price + slippage.

        For limit orders:
            - Buy limit: fills if bar's low <= limit price.
              Fill price is min(open, limit_price).
            - Sell limit: fills if bar's high >= limit price.
              Fill price is max(open, limit_price).

        Args:
            order: The order to fill.
            bar: OHLCV data for the execution bar.

        Returns:
            Fill price after slippage, or None if limit order doesn't fill.
        """
        if order.order_type == OrderType.MARKET:
            base_price = bar["open"]
            slippage = self._calculate_slippage(base_price, order.side)
            return base_price + slippage

        elif order.order_type == OrderType.LIMIT:
            if order.limit_price is None:
                logger.error("Limit order missing limit_price, rejecting")
                return None

            # Limit orders do NOT have slippage applied. In real markets,
            # a buy limit fills at or below the limit price, and a sell
            # limit fills at or above. Adding slippage would violate
            # these guarantees.
            if order.is_buy:
                # Buy limit fills if price drops to or below limit
                if bar["low"] <= order.limit_price:
                    return min(bar["open"], order.limit_price)
                return None  # Didn't fill
            else:
                # Sell limit fills if price rises to or above limit
                if bar["high"] >= order.limit_price:
                    return max(bar["open"], order.limit_price)
                return None  # Didn't fill

        return None

    def calculate_fees(self, fill_price: float, quantity: float) -> float:
        """Calculate transaction fees.

        Args:
            fill_price: Price at which the order was filled.
            quantity: Number of units traded.

        Returns:
            Total fee amount.
        """
        trade_value = abs(fill_price * quantity)
        return trade_value * self.fee_rate

    def execute_order(
        self,
        order: Order,
        bar: pd.Series,
        bar_timestamp: datetime,
    ) -> bool:
        """Attempt to execute an order against a bar.

        Modifies the order in-place with fill details.

        Args:
            order: The order to execute.
            bar: OHLCV data for the execution bar.
            bar_timestamp: Timestamp of the execution bar.

        Returns:
            True if the order was filled, False otherwise.
        """
        fill_price = self.calculate_fill_price(order, bar)

        if fill_price is None:
            if order.order_type == OrderType.LIMIT:
                logger.debug(
                    f"Limit order not filled: {order.side.value} "
                    f"limit={order.limit_price}, bar range=[{bar['low']}, {bar['high']}]"
                )
            return False

        fees = self.calculate_fees(fill_price, order.quantity)
        slippage_amount = abs(fill_price - bar["open"])

        order.mark_filled(
            fill_price=fill_price,
            fill_timestamp=bar_timestamp,
            fees=fees,
            slippage=slippage_amount,
        )

        logger.debug(
            f"Order filled: {order.side.value} {order.quantity:.4f} @ {fill_price:.4f} "
            f"(fees={fees:.4f}, slippage={slippage_amount:.4f})"
        )

        return True

    def _calculate_slippage(self, base_price: float, side: OrderSide) -> float:
        """Calculate slippage amount.

        Buys slip up (worse fill), sells slip down (worse fill).

        Args:
            base_price: The base execution price before slippage.
            side: Buy or sell.

        Returns:
            Signed slippage amount.
        """
        slippage = base_price * self.slippage_rate
        if side == OrderSide.BUY:
            return slippage  # Buyer pays more
        else:
            return -slippage  # Seller receives less
