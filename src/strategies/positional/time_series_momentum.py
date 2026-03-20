"""Time-series momentum strategy."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal


@dataclass
class TimeSeriesMomentumConfig:
    lookback: int = 63
    min_return_pct: float = 0.03
    trend_filter_period: int = 50


class TimeSeriesMomentumStrategy(BaseStrategy):
    """
    Trend/momentum continuation based on trailing returns.

    BUY when return over lookback exceeds threshold and trend filter is positive.
    SELL for strongly negative momentum.
    """

    config: TimeSeriesMomentumConfig

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        cfg = TimeSeriesMomentumConfig(
            lookback=int(self.get_param("lookback", 63)),
            min_return_pct=float(self.get_param("min_return_pct", 0.03)),
            trend_filter_period=int(self.get_param("trend_filter_period", 50)),
        )
        if cfg.lookback < 5:
            raise ValueError("lookback must be >= 5")
        if cfg.trend_filter_period < 5:
            raise ValueError("trend_filter_period must be >= 5")
        if cfg.min_return_pct < 0:
            raise ValueError("min_return_pct must be >= 0")
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
        min_bars = max(self.config.lookback + 1, self.config.trend_filter_period + 1)
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
        close_now = float(close.iloc[-1])
        close_ref = float(close.iloc[-(self.config.lookback + 1)])
        if close_ref == 0:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="invalid_reference_price",
            )

        momentum_ret = (close_now - close_ref) / close_ref
        trend_ma = self.sma(close, self.config.trend_filter_period).iloc[-1]
        if pd.isna(trend_ma):
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="trend_filter_unavailable",
            )

        action = Signal.HOLD
        rationale = "no_momentum_signal"
        if momentum_ret >= self.config.min_return_pct and close_now > float(trend_ma):
            action = Signal.BUY
            rationale = "positive_momentum_continuation"
        elif momentum_ret <= -self.config.min_return_pct and close_now < float(trend_ma):
            action = Signal.SELL
            rationale = "negative_momentum_continuation"
        elif close_now < float(trend_ma):
            action = Signal.EXIT
            rationale = "trend_filter_exit"

        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=0.75 if action != Signal.HOLD else 0.0,
            rationale=rationale,
            tags=("positional", "momentum", "trend"),
            metadata={
                "momentum_return_pct": float(momentum_ret),
                "trend_filter_ma": float(trend_ma),
                "lookback": self.config.lookback,
            },
        )

    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return self.generate_signal(data, current_bar, bar_index).action

