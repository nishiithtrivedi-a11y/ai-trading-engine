"""
Donchian Breakout strategy.

Enters long when price breaks above the Donchian Channel upper band.
Exits when price breaks below the Donchian Channel lower band.
"""

from __future__ import annotations

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal


class BreakoutStrategy(BaseStrategy):
    """Donchian Channel breakout strategy.

    Enters on breakout above the N-period high.
    Exits on breakdown below the M-period low.

    Parameters:
        entry_period (int): Lookback for upper band. Default: 20.
        exit_period (int): Lookback for lower band. Default: 10.
    """

    @property
    def name(self) -> str:
        entry_p = self.get_param("entry_period", 20)
        exit_p = self.get_param("exit_period", 10)
        return f"Breakout({entry_p},{exit_p})"

    def on_bar(
        self,
        data: pd.DataFrame,
        current_bar: pd.Series,
        bar_index: int,
    ) -> Signal:
        entry_period = self.get_param("entry_period", 20)
        exit_period = self.get_param("exit_period", 10)

        min_period = max(entry_period, exit_period) + 1
        if len(data) < min_period:
            return Signal.HOLD

        # Use previous bars for the channel (exclude current bar to avoid lookahead)
        # The channel is based on data up to the previous bar
        prev_data = data.iloc[:-1]

        upper = self.donchian_high(prev_data["high"], entry_period)
        lower = self.donchian_low(prev_data["low"], exit_period)

        upper_val = upper.iloc[-1]
        lower_val = lower.iloc[-1]

        if pd.isna(upper_val) or pd.isna(lower_val):
            return Signal.HOLD

        current_close = current_bar["close"]

        # Breakout above upper band => buy
        if current_close > upper_val:
            return Signal.BUY

        # Breakdown below lower band => exit
        if current_close < lower_val:
            return Signal.EXIT

        return Signal.HOLD
