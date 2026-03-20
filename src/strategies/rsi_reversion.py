"""
RSI Mean Reversion strategy.

Enters long when RSI drops below the oversold threshold.
Exits when RSI rises above the overbought threshold.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal


@dataclass
class RSIReversionConfig:
    rsi_period: int = 14
    oversold: float = 30.0
    overbought: float = 70.0


class RSIReversionStrategy(BaseStrategy):
    """RSI-based mean reversion strategy.

    Buys when RSI indicates oversold conditions, sells when
    RSI indicates overbought conditions.

    Parameters:
        rsi_period (int): RSI calculation period. Default: 14.
        oversold (float): RSI level below which to buy. Default: 30.
        overbought (float): RSI level above which to exit. Default: 70.
    """
    config: RSIReversionConfig

    @property
    def name(self) -> str:
        cfg = getattr(self, "config", RSIReversionConfig())
        period = cfg.rsi_period
        lo = cfg.oversold
        hi = cfg.overbought
        return f"RSI_Reversion({period},{lo},{hi})"

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        rsi_period = int(self.get_param("rsi_period", RSIReversionConfig.rsi_period))
        oversold = float(self.get_param("oversold", RSIReversionConfig.oversold))
        overbought = float(self.get_param("overbought", RSIReversionConfig.overbought))
        if rsi_period <= 0:
            raise ValueError("rsi_period must be a positive integer")
        self.config = RSIReversionConfig(
            rsi_period=rsi_period,
            oversold=oversold,
            overbought=overbought,
        )

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

        rsi_period = self.config.rsi_period
        oversold = self.config.oversold
        overbought = self.config.overbought

        # Need enough bars for RSI
        if len(data) < rsi_period + 2:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="insufficient_bars_for_rsi",
                metadata={
                    "bars_available": len(data),
                    "bars_required": rsi_period + 2,
                    "rsi_period": rsi_period,
                },
            )

        close = data["close"]
        rsi_series = self.rsi(close, rsi_period)
        current_rsi = rsi_series.iloc[-1]

        if pd.isna(current_rsi):
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="indicator_warmup",
                metadata={"rsi_period": rsi_period},
            )

        action = Signal.HOLD
        rationale = "neutral_rsi"

        # Oversold => buy
        if current_rsi < oversold:
            action = Signal.BUY
            rationale = "oversold_reversion"

        # Overbought => exit
        elif current_rsi > overbought:
            action = Signal.EXIT
            rationale = "overbought_reversion_exit"

        confidence = 0.0 if action == Signal.HOLD else 0.7
        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=confidence,
            rationale=rationale,
            tags=("mean_reversion", "rsi"),
            metadata={
                "rsi_period": rsi_period,
                "oversold": oversold,
                "overbought": overbought,
                "rsi_value": float(current_rsi),
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
