"""Gap continuation and gap-fade intraday strategies."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal


@dataclass
class GapStrategyConfig:
    min_gap_pct: float = 0.01
    timezone: str = "Asia/Kolkata"


def _day_open_and_prev_close(data: pd.DataFrame, timezone: str) -> tuple[float, float] | None:
    if not isinstance(data.index, pd.DatetimeIndex):
        raise ValueError("Gap strategies require DatetimeIndex data")
    if len(data) < 3:
        return None

    idx = data.index
    if "_cached_local_ts" in data.columns:
        local_idx = pd.DatetimeIndex(data["_cached_local_ts"])
    elif idx.tz is None:
        local_idx = idx.tz_localize("UTC").tz_convert(timezone)
    else:
        local_idx = idx.tz_convert(timezone)

    day_keys = pd.Series(local_idx.date, index=data.index)
    current_day = day_keys.iloc[-1]
    today_mask = day_keys == current_day
    prev_mask = day_keys < current_day
    if not prev_mask.any() or not today_mask.any():
        return None

    day_open = float(data.loc[today_mask, "open"].iloc[0])
    prev_close = float(data.loc[prev_mask, "close"].iloc[-1])
    return day_open, prev_close


class GapMomentumStrategy(BaseStrategy):
    """Gap-and-go continuation strategy."""

    config: GapStrategyConfig

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        cfg = GapStrategyConfig(
            min_gap_pct=float(self.get_param("min_gap_pct", 0.01)),
            timezone=str(self.get_param("timezone", "Asia/Kolkata")),
        )
        if cfg.min_gap_pct <= 0:
            raise ValueError("min_gap_pct must be > 0")
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
        self.require_columns(data, ["open", "close"])

        pair = _day_open_and_prev_close(data, self.config.timezone)
        if pair is None:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="insufficient_day_context",
            )
        day_open, prev_close = pair
        gap_pct = (day_open - prev_close) / prev_close if prev_close != 0 else 0.0
        close_now = float(current_bar["close"])

        action = Signal.HOLD
        rationale = "no_gap_continuation"
        if gap_pct >= self.config.min_gap_pct and close_now > day_open:
            action = Signal.BUY
            rationale = "gap_up_continuation"
        elif gap_pct <= -self.config.min_gap_pct and close_now < day_open:
            action = Signal.SELL
            rationale = "gap_down_continuation"

        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=0.7 if action != Signal.HOLD else 0.0,
            rationale=rationale,
            tags=("intraday", "gap", "momentum"),
            metadata={
                "day_open": day_open,
                "prev_close": prev_close,
                "gap_pct": float(gap_pct),
            },
        )

    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return self.generate_signal(data, current_bar, bar_index).action


class GapFadeStrategy(BaseStrategy):
    """Gap-fade intraday strategy."""

    config: GapStrategyConfig

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        cfg = GapStrategyConfig(
            min_gap_pct=float(self.get_param("min_gap_pct", 0.01)),
            timezone=str(self.get_param("timezone", "Asia/Kolkata")),
        )
        if cfg.min_gap_pct <= 0:
            raise ValueError("min_gap_pct must be > 0")
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
        self.require_columns(data, ["open", "close"])

        pair = _day_open_and_prev_close(data, self.config.timezone)
        if pair is None:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="insufficient_day_context",
            )
        day_open, prev_close = pair
        gap_pct = (day_open - prev_close) / prev_close if prev_close != 0 else 0.0
        close_now = float(current_bar["close"])

        action = Signal.HOLD
        rationale = "no_gap_fade_setup"
        if gap_pct >= self.config.min_gap_pct and close_now < day_open:
            action = Signal.SELL
            rationale = "gap_up_fade"
        elif gap_pct <= -self.config.min_gap_pct and close_now > day_open:
            action = Signal.BUY
            rationale = "gap_down_fade"

        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=0.65 if action != Signal.HOLD else 0.0,
            rationale=rationale,
            tags=("intraday", "gap", "mean_reversion"),
            metadata={
                "day_open": day_open,
                "prev_close": prev_close,
                "gap_pct": float(gap_pct),
            },
        )

    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return self.generate_signal(data, current_bar, bar_index).action

