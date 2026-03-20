"""
Donchian Breakout strategy.

Enters long when price breaks above the Donchian Channel upper band.
Exits when price breaks below the Donchian Channel lower band.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal


@dataclass
class BreakoutConfig:
    entry_period: int = 20
    exit_period: int = 10


class BreakoutStrategy(BaseStrategy):
    """Donchian Channel breakout strategy.

    Enters on breakout above the N-period high.
    Exits on breakdown below the M-period low.

    Parameters:
        entry_period (int): Lookback for upper band. Default: 20.
        exit_period (int): Lookback for lower band. Default: 10.
    """
    config: BreakoutConfig

    @property
    def name(self) -> str:
        cfg = getattr(self, "config", BreakoutConfig())
        entry_p = cfg.entry_period
        exit_p = cfg.exit_period
        return f"Breakout({entry_p},{exit_p})"

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        entry_period = int(self.get_param("entry_period", BreakoutConfig.entry_period))
        exit_period = int(self.get_param("exit_period", BreakoutConfig.exit_period))
        if entry_period <= 0 or exit_period <= 0:
            raise ValueError("entry_period and exit_period must be positive integers")
        self.config = BreakoutConfig(entry_period=entry_period, exit_period=exit_period)

    def generate_signal(
        self,
        data: pd.DataFrame,
        current_bar: pd.Series,
        bar_index: int,
        *,
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> StrategySignal:
        if not getattr(self, "_is_initialized", False):
            self.initialize()

        entry_period = self.config.entry_period
        exit_period = self.config.exit_period

        min_period = max(entry_period, exit_period) + 1
        if len(data) < min_period:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="insufficient_bars_for_donchian",
                metadata={
                    "bars_available": len(data),
                    "bars_required": min_period,
                    "entry_period": entry_period,
                    "exit_period": exit_period,
                },
            )

        # Use previous bars for the channel (exclude current bar to avoid lookahead)
        # The channel is based on data up to the previous bar.
        prev_data = data.iloc[:-1]
        upper = self.donchian_high(prev_data["high"], entry_period)
        lower = self.donchian_low(prev_data["low"], exit_period)

        upper_val = upper.iloc[-1]
        lower_val = lower.iloc[-1]

        if pd.isna(upper_val) or pd.isna(lower_val):
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="indicator_warmup",
                metadata={
                    "entry_period": entry_period,
                    "exit_period": exit_period,
                },
            )

        current_close = float(current_bar["close"])

        action = Signal.HOLD
        rationale = "inside_channel"

        # Breakout above upper band => buy
        if current_close > upper_val:
            action = Signal.BUY
            rationale = "breakout_above_upper_band"

        # Breakdown below lower band => exit
        elif current_close < lower_val:
            action = Signal.EXIT
            rationale = "breakdown_below_lower_band"

        confidence = 0.0 if action == Signal.HOLD else 0.85
        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=confidence,
            rationale=rationale,
            tags=("breakout", "donchian"),
            metadata={
                "entry_period": entry_period,
                "exit_period": exit_period,
                "upper_band": float(upper_val),
                "lower_band": float(lower_val),
                "close": current_close,
            },
        )

    def on_bar(
        self,
        data: pd.DataFrame,
        current_bar: pd.Series,
        bar_index: int,
    ) -> Signal:
        return self.generate_signal(
            data=data,
            current_bar=current_bar,
            bar_index=bar_index,
        ).action
