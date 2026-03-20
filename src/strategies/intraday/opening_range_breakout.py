"""Opening range breakout strategy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal


@dataclass
class OpeningRangeBreakoutConfig:
    session_start: str = "09:15"
    opening_range_minutes: int = 30
    timezone: str = "Asia/Kolkata"
    breakout_buffer_pct: float = 0.0
    direction: str = "both"  # long | short | both


class OpeningRangeBreakoutStrategy(BaseStrategy):
    """
    Opening range breakout for intraday bars.

    Standard interpretation:
    - Build high/low of first N minutes from session open.
    - Break above range high -> BUY.
    - Break below range low -> SELL (short-side signal).
    """

    config: OpeningRangeBreakoutConfig

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        cfg = OpeningRangeBreakoutConfig(
            session_start=str(self.get_param("session_start", "09:15")),
            opening_range_minutes=int(self.get_param("opening_range_minutes", 30)),
            timezone=str(self.get_param("timezone", "Asia/Kolkata")),
            breakout_buffer_pct=float(self.get_param("breakout_buffer_pct", 0.0)),
            direction=str(self.get_param("direction", "both")).strip().lower(),
        )
        if cfg.opening_range_minutes < 5:
            raise ValueError("opening_range_minutes must be >= 5")
        if cfg.breakout_buffer_pct < 0:
            raise ValueError("breakout_buffer_pct must be >= 0")
        if cfg.direction not in {"long", "short", "both"}:
            raise ValueError("direction must be one of: long, short, both")
        self.config = cfg

    @property
    def name(self) -> str:
        cfg = getattr(self, "config", OpeningRangeBreakoutConfig())
        return f"OpeningRangeBreakout({cfg.opening_range_minutes}m,{cfg.direction})"

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
            raise ValueError("OpeningRangeBreakoutStrategy requires DatetimeIndex data")
        if len(data) < 3:
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

        current_local_ts = local_idx[-1]
        day_start = pd.Timestamp(
            f"{current_local_ts.date()} {self.config.session_start}",
            tz=self.config.timezone,
        )
        day_end = day_start + timedelta(minutes=self.config.opening_range_minutes)

        opening_mask = (local_idx >= day_start) & (local_idx < day_end)
        if opening_mask.sum() < 2:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="opening_window_not_complete",
            )

        # Do not trigger while still inside opening window.
        if current_local_ts < day_end:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="inside_opening_window",
            )

        opening_data = data.loc[opening_mask]
        range_high = float(opening_data["high"].max())
        range_low = float(opening_data["low"].min())
        close = float(current_bar["close"])

        up_level = range_high * (1.0 + self.config.breakout_buffer_pct)
        down_level = range_low * (1.0 - self.config.breakout_buffer_pct)

        action = Signal.HOLD
        rationale = "inside_range"
        if close > up_level and self.config.direction in {"long", "both"}:
            action = Signal.BUY
            rationale = "opening_range_breakout_up"
        elif close < down_level and self.config.direction in {"short", "both"}:
            action = Signal.SELL
            rationale = "opening_range_breakdown"

        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=0.75 if action != Signal.HOLD else 0.0,
            rationale=rationale,
            tags=("intraday", "breakout", "opening_range"),
            metadata={
                "range_high": range_high,
                "range_low": range_low,
                "up_level": up_level,
                "down_level": down_level,
                "direction": self.config.direction,
            },
        )

    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return self.generate_signal(data, current_bar, bar_index).action

