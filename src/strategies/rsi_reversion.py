"""
RSI Mean Reversion strategy.

Enters long when RSI drops below the oversold threshold.
Exits when RSI rises above the overbought threshold.
"""

from __future__ import annotations

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal


class RSIReversionStrategy(BaseStrategy):
    """RSI-based mean reversion strategy.

    Buys when RSI indicates oversold conditions, sells when
    RSI indicates overbought conditions.

    Parameters:
        rsi_period (int): RSI calculation period. Default: 14.
        oversold (float): RSI level below which to buy. Default: 30.
        overbought (float): RSI level above which to exit. Default: 70.
    """

    @property
    def name(self) -> str:
        period = self.get_param("rsi_period", 14)
        lo = self.get_param("oversold", 30)
        hi = self.get_param("overbought", 70)
        return f"RSI_Reversion({period},{lo},{hi})"

    def on_bar(
        self,
        data: pd.DataFrame,
        current_bar: pd.Series,
        bar_index: int,
    ) -> Signal:
        rsi_period = self.get_param("rsi_period", 14)
        oversold = self.get_param("oversold", 30)
        overbought = self.get_param("overbought", 70)

        # Need enough bars for RSI
        if len(data) < rsi_period + 2:
            return Signal.HOLD

        close = data["close"]
        rsi_series = self.rsi(close, rsi_period)

        current_rsi = rsi_series.iloc[-1]

        if pd.isna(current_rsi):
            return Signal.HOLD

        # Oversold => buy
        if current_rsi < oversold:
            return Signal.BUY

        # Overbought => exit
        if current_rsi > overbought:
            return Signal.EXIT

        return Signal.HOLD
