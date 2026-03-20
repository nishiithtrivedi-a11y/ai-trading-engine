"""Price-channel breakout strategy."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal


@dataclass
class PriceChannelBreakoutConfig:
    lookback: int = 55
    direction: str = "both"  # long | short | both
    use_close_break: bool = True


class PriceChannelBreakoutStrategy(BaseStrategy):
    """Break out of rolling high/low channel built from prior bars."""

    config: PriceChannelBreakoutConfig

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        cfg = PriceChannelBreakoutConfig(
            lookback=int(self.get_param("lookback", 55)),
            direction=str(self.get_param("direction", "both")).strip().lower(),
            use_close_break=bool(self.get_param("use_close_break", True)),
        )
        if cfg.lookback < 5:
            raise ValueError("lookback must be >= 5")
        if cfg.direction not in {"long", "short", "both"}:
            raise ValueError("direction must be one of: long, short, both")
        self.config = cfg

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
        self.require_columns(data, ["high", "low", "close"])
        if len(data) < self.config.lookback + 1:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="insufficient_bars",
            )

        prev = data.iloc[:-1]
        channel_high = float(prev["high"].tail(self.config.lookback).max())
        channel_low = float(prev["low"].tail(self.config.lookback).min())
        close_now = float(current_bar["close"])
        high_now = float(current_bar["high"])
        low_now = float(current_bar["low"])
        trigger_up = close_now if self.config.use_close_break else high_now
        trigger_down = close_now if self.config.use_close_break else low_now

        action = Signal.HOLD
        rationale = "inside_channel"
        if trigger_up > channel_high and self.config.direction in {"long", "both"}:
            action = Signal.BUY
            rationale = "channel_breakout_up"
        elif trigger_down < channel_low and self.config.direction in {"short", "both"}:
            action = Signal.SELL
            rationale = "channel_breakout_down"
        elif close_now < channel_low and self.config.direction in {"long", "both"}:
            action = Signal.EXIT
            rationale = "long_breakdown_exit"

        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=0.8 if action != Signal.HOLD else 0.0,
            rationale=rationale,
            tags=("swing", "breakout", "price_channel"),
            metadata={
                "channel_high": channel_high,
                "channel_low": channel_low,
                "lookback": self.config.lookback,
                "use_close_break": self.config.use_close_break,
            },
        )

    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return self.generate_signal(data, current_bar, bar_index).action

