"""
SMA Crossover strategy.

Enters long when the fast SMA crosses above the slow SMA.
Exits when the fast SMA crosses below the slow SMA.
"""

from __future__ import annotations

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal


class SMACrossoverStrategy(BaseStrategy):
    """Simple Moving Average crossover strategy.

    Parameters:
        fast_period (int): Fast SMA lookback period. Default: 10.
        slow_period (int): Slow SMA lookback period. Default: 30.
    """

    @property
    def name(self) -> str:
        fast = self.get_param("fast_period", 10)
        slow = self.get_param("slow_period", 30)
        return f"SMA_Crossover({fast},{slow})"

    def on_bar(
        self,
        data: pd.DataFrame,
        current_bar: pd.Series,
        bar_index: int,
    ) -> Signal:
        fast_period = self.get_param("fast_period", 10)
        slow_period = self.get_param("slow_period", 30)

        # Need at least slow_period + 1 bars to detect a crossover
        if len(data) < slow_period + 1:
            return Signal.HOLD

        close = data["close"]
        fast_sma = self.sma(close, fast_period)
        slow_sma = self.sma(close, slow_period)

        # Current and previous values
        fast_now = fast_sma.iloc[-1]
        fast_prev = fast_sma.iloc[-2]
        slow_now = slow_sma.iloc[-1]
        slow_prev = slow_sma.iloc[-2]

        # Check for NaN (insufficient data for indicator)
        if pd.isna(fast_now) or pd.isna(slow_now) or pd.isna(fast_prev) or pd.isna(slow_prev):
            return Signal.HOLD

        # Bullish crossover: fast crosses above slow
        if fast_prev <= slow_prev and fast_now > slow_now:
            return Signal.BUY

        # Bearish crossover: fast crosses below slow
        if fast_prev >= slow_prev and fast_now < slow_now:
            return Signal.EXIT

        return Signal.HOLD
