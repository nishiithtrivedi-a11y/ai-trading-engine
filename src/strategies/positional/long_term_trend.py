"""Long-term trend filter strategy."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal


@dataclass
class LongTermTrendConfig:
    trend_period: int = 200
    fast_period: int = 50


class LongTermTrendStrategy(BaseStrategy):
    """
    Long-term trend model (200DMA style).

    BUY when fast trend is above long trend and price is above long trend.
    EXIT when price falls below long trend.
    """

    config: LongTermTrendConfig

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        cfg = LongTermTrendConfig(
            trend_period=int(self.get_param("trend_period", 200)),
            fast_period=int(self.get_param("fast_period", 50)),
        )
        if cfg.trend_period < 20 or cfg.fast_period < 5:
            raise ValueError("trend_period must be >= 20 and fast_period >= 5")
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
        self.require_columns(data, ["close"])
        min_bars = max(self.config.trend_period, self.config.fast_period) + 1
        if len(data) < min_bars:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="insufficient_bars",
            )

        close = data["close"].astype(float)
        long_ma = self.sma(close, self.config.trend_period).iloc[-1]
        fast_ma = self.sma(close, self.config.fast_period).iloc[-1]
        close_now = float(close.iloc[-1])

        if pd.isna(long_ma) or pd.isna(fast_ma):
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="indicator_warmup",
            )

        action = Signal.HOLD
        rationale = "trend_unclear"
        if close_now > float(long_ma) and float(fast_ma) >= float(long_ma):
            action = Signal.BUY
            rationale = "long_term_uptrend"
        elif close_now < float(long_ma):
            action = Signal.EXIT
            rationale = "long_term_trend_break"

        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=0.8 if action != Signal.HOLD else 0.0,
            rationale=rationale,
            tags=("positional", "trend_following"),
            metadata={
                "long_ma": float(long_ma),
                "fast_ma": float(fast_ma),
                "trend_period": self.config.trend_period,
                "fast_period": self.config.fast_period,
            },
        )

    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return self.generate_signal(data, current_bar, bar_index).action

