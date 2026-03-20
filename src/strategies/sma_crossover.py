"""
SMA Crossover strategy.

Enters long when the fast SMA crosses above the slow SMA.
Exits when the fast SMA crosses below the slow SMA.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal


@dataclass
class SMACrossoverConfig:
    fast_period: int = 10
    slow_period: int = 30


class SMACrossoverStrategy(BaseStrategy):
    """Simple Moving Average crossover strategy.

    Parameters:
        fast_period (int): Fast SMA lookback period. Default: 10.
        slow_period (int): Slow SMA lookback period. Default: 30.
    """
    config: SMACrossoverConfig

    @property
    def name(self) -> str:
        cfg = getattr(self, "config", SMACrossoverConfig())
        fast = cfg.fast_period
        slow = cfg.slow_period
        return f"SMA_Crossover({fast},{slow})"

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        fast = int(self.get_param("fast_period", SMACrossoverConfig.fast_period))
        slow = int(self.get_param("slow_period", SMACrossoverConfig.slow_period))
        if fast <= 0 or slow <= 0:
            raise ValueError("fast_period and slow_period must be positive integers")
        self.config = SMACrossoverConfig(fast_period=fast, slow_period=slow)

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

        fast_period = self.config.fast_period
        slow_period = self.config.slow_period

        # Need at least slow_period + 1 bars to detect a crossover
        if len(data) < slow_period + 1:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="insufficient_bars_for_crossover",
                metadata={
                    "bars_available": len(data),
                    "bars_required": slow_period + 1,
                    "fast_period": fast_period,
                    "slow_period": slow_period,
                },
            )

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
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="indicator_warmup",
                metadata={
                    "fast_period": fast_period,
                    "slow_period": slow_period,
                },
            )

        action = Signal.HOLD
        rationale = "no_crossover"

        # Bullish crossover: fast crosses above slow
        if fast_prev <= slow_prev and fast_now > slow_now:
            action = Signal.BUY
            rationale = "bullish_crossover"

        # Bearish crossover: fast crosses below slow
        elif fast_prev >= slow_prev and fast_now < slow_now:
            action = Signal.EXIT
            rationale = "bearish_crossover"

        confidence = 0.0 if action == Signal.HOLD else 0.8
        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=confidence,
            rationale=rationale,
            tags=("trend", "moving_average"),
            metadata={
                "fast_period": fast_period,
                "slow_period": slow_period,
                "fast_sma": float(fast_now),
                "slow_sma": float(slow_now),
                "sma_spread": float(fast_now - slow_now),
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
