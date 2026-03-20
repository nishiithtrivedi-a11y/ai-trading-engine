"""Relative-volume breakout strategy."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal


@dataclass
class RelativeVolumeBreakoutConfig:
    volume_lookback: int = 20
    volume_multiplier: float = 1.8
    breakout_lookback: int = 20
    direction: str = "both"  # long | short | both


class RelativeVolumeBreakoutStrategy(BaseStrategy):
    """Breakout signal gated by relative-volume expansion."""

    config: RelativeVolumeBreakoutConfig

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        cfg = RelativeVolumeBreakoutConfig(
            volume_lookback=int(self.get_param("volume_lookback", 20)),
            volume_multiplier=float(self.get_param("volume_multiplier", 1.8)),
            breakout_lookback=int(self.get_param("breakout_lookback", 20)),
            direction=str(self.get_param("direction", "both")).strip().lower(),
        )
        if cfg.volume_lookback < 2:
            raise ValueError("volume_lookback must be >= 2")
        if cfg.breakout_lookback < 2:
            raise ValueError("breakout_lookback must be >= 2")
        if cfg.volume_multiplier <= 1.0:
            raise ValueError("volume_multiplier must be > 1.0")
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

        self.require_columns(data, ["high", "low", "close", "volume"])
        min_bars = max(self.config.volume_lookback, self.config.breakout_lookback) + 1
        if len(data) < min_bars:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="insufficient_bars",
            )

        prev = data.iloc[:-1]
        avg_volume = prev["volume"].tail(self.config.volume_lookback).mean()
        if pd.isna(avg_volume) or float(avg_volume) <= 0:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="invalid_volume_context",
            )

        current_volume = float(current_bar["volume"])
        if current_volume < float(avg_volume) * self.config.volume_multiplier:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="volume_not_expanded",
                metadata={
                    "current_volume": current_volume,
                    "avg_volume": float(avg_volume),
                },
            )

        range_high = float(prev["high"].tail(self.config.breakout_lookback).max())
        range_low = float(prev["low"].tail(self.config.breakout_lookback).min())
        close_now = float(current_bar["close"])

        action = Signal.HOLD
        rationale = "inside_breakout_range"
        if close_now > range_high and self.config.direction in {"long", "both"}:
            action = Signal.BUY
            rationale = "relative_volume_breakout_up"
        elif close_now < range_low and self.config.direction in {"short", "both"}:
            action = Signal.SELL
            rationale = "relative_volume_breakout_down"

        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=0.8 if action != Signal.HOLD else 0.0,
            rationale=rationale,
            tags=("intraday", "volume", "breakout"),
            metadata={
                "range_high": range_high,
                "range_low": range_low,
                "current_volume": current_volume,
                "average_volume": float(avg_volume),
                "volume_multiple": current_volume / float(avg_volume),
            },
        )

    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return self.generate_signal(data, current_bar, bar_index).action

