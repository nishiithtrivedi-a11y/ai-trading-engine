"""Moving-average pullback continuation strategy."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal


@dataclass
class MovingAveragePullbackConfig:
    trend_period: int = 50
    pullback_period: int = 20
    pullback_tolerance_pct: float = 0.01


class MovingAveragePullbackStrategy(BaseStrategy):
    """
    Trend continuation after pullback to a moving average.

    Standard interpretation:
    - Trend filter: close above long MA.
    - Pullback zone: close near/below short MA.
    - Re-entry trigger: close recovers above previous close in uptrend.
    """

    config: MovingAveragePullbackConfig

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        cfg = MovingAveragePullbackConfig(
            trend_period=int(self.get_param("trend_period", 50)),
            pullback_period=int(self.get_param("pullback_period", 20)),
            pullback_tolerance_pct=float(self.get_param("pullback_tolerance_pct", 0.01)),
        )
        if cfg.trend_period < 5 or cfg.pullback_period < 2:
            raise ValueError("trend_period must be >= 5 and pullback_period >= 2")
        if cfg.pullback_tolerance_pct < 0:
            raise ValueError("pullback_tolerance_pct must be >= 0")
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
        min_bars = max(self.config.trend_period, self.config.pullback_period) + 2
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
        trend_ma = self.sma(close, self.config.trend_period)
        pullback_ma = self.sma(close, self.config.pullback_period)

        trend_now = trend_ma.iloc[-1]
        pullback_now = pullback_ma.iloc[-1]
        close_now = float(close.iloc[-1])
        close_prev = float(close.iloc[-2])

        if pd.isna(trend_now) or pd.isna(pullback_now):
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="indicator_warmup",
            )

        tolerance = float(pullback_now) * self.config.pullback_tolerance_pct
        in_uptrend = close_now > float(trend_now)
        pullback_zone = close_now <= float(pullback_now) + tolerance
        bounce = close_now > close_prev

        action = Signal.HOLD
        rationale = "no_pullback_continuation"
        if in_uptrend and pullback_zone and bounce:
            action = Signal.BUY
            rationale = "uptrend_pullback_bounce"
        elif close_now < float(trend_now):
            action = Signal.EXIT
            rationale = "trend_filter_broken"

        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=0.75 if action != Signal.HOLD else 0.0,
            rationale=rationale,
            tags=("swing", "trend_following", "pullback"),
            metadata={
                "trend_ma": float(trend_now),
                "pullback_ma": float(pullback_now),
                "pullback_tolerance_pct": self.config.pullback_tolerance_pct,
            },
        )

    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return self.generate_signal(data, current_bar, bar_index).action

