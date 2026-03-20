"""Intraday day-high/day-low breakout strategy."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal


@dataclass
class DayHighLowBreakoutConfig:
    timezone: str = "Asia/Kolkata"
    direction: str = "both"  # long | short | both
    min_bars_in_session: int = 6


class DayHighLowBreakoutStrategy(BaseStrategy):
    """
    Break intraday session extremes built from prior bars of the same day.

    - BUY on breakout above current-day prior high.
    - SELL on breakdown below current-day prior low.
    """

    config: DayHighLowBreakoutConfig

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        cfg = DayHighLowBreakoutConfig(
            timezone=str(self.get_param("timezone", "Asia/Kolkata")),
            direction=str(self.get_param("direction", "both")).strip().lower(),
            min_bars_in_session=int(self.get_param("min_bars_in_session", 6)),
        )
        if cfg.direction not in {"long", "short", "both"}:
            raise ValueError("direction must be one of: long, short, both")
        if cfg.min_bars_in_session < 2:
            raise ValueError("min_bars_in_session must be >= 2")
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
        if not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError("DayHighLowBreakoutStrategy requires DatetimeIndex data")
        if len(data) < self.config.min_bars_in_session + 1:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="insufficient_bars",
            )

        idx = data.index
        if idx.tz is None:
            local_idx = idx.tz_localize("UTC").tz_convert(self.config.timezone)
        else:
            local_idx = idx.tz_convert(self.config.timezone)

        day_keys = pd.Series(local_idx.date, index=data.index)
        current_day = day_keys.iloc[-1]
        today_data = data.loc[day_keys == current_day]
        if len(today_data) <= self.config.min_bars_in_session:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="session_warmup",
            )

        prior_today = today_data.iloc[:-1]
        session_high = float(prior_today["high"].max())
        session_low = float(prior_today["low"].min())
        close_now = float(current_bar["close"])

        action = Signal.HOLD
        rationale = "inside_day_range"
        if close_now > session_high and self.config.direction in {"long", "both"}:
            action = Signal.BUY
            rationale = "day_high_breakout"
        elif close_now < session_low and self.config.direction in {"short", "both"}:
            action = Signal.SELL
            rationale = "day_low_breakdown"

        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=0.74 if action != Signal.HOLD else 0.0,
            rationale=rationale,
            tags=("intraday", "momentum", "day_high_low"),
            metadata={
                "session_high": session_high,
                "session_low": session_low,
                "direction": self.config.direction,
            },
        )

    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return self.generate_signal(data, current_bar, bar_index).action

