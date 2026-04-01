"""Gap continuation and gap-fade intraday strategies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal


@dataclass
class GapStrategyConfig:
    min_gap_pct: float = 0.01
    timezone: str = "Asia/Kolkata"
    entry_start: str | None = None
    entry_end: str | None = None


def _parse_hhmm(value: str, *, field_name: str) -> time:
    clean = str(value).strip()
    try:
        parsed = pd.to_datetime(clean, format="%H:%M")
    except ValueError as exc:
        raise ValueError(f"{field_name} must be HH:MM (24-hour) format") from exc
    return parsed.time()


def _in_window(now: time, start: time, end: time) -> bool:
    return start <= now <= end


def _local_index(data: pd.DataFrame, timezone: str) -> pd.DatetimeIndex:
    if not isinstance(data.index, pd.DatetimeIndex):
        raise ValueError("Gap strategies require DatetimeIndex data")
    idx = data.index
    if "_cached_local_ts" in data.columns:
        return pd.DatetimeIndex(data["_cached_local_ts"])
    if idx.tz is None:
        return idx.tz_localize("UTC").tz_convert(timezone)
    return idx.tz_convert(timezone)


def _day_open_and_prev_close(data: pd.DataFrame, timezone: str) -> tuple[float, float] | None:
    if len(data) < 3:
        return None

    local_idx = _local_index(data, timezone)
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
    _entry_start: time | None
    _entry_end: time | None

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        cfg = GapStrategyConfig(
            min_gap_pct=float(self.get_param("min_gap_pct", 0.01)),
            timezone=str(self.get_param("timezone", "Asia/Kolkata")),
            entry_start=self.get_param("entry_start", None),  # type: ignore[arg-type]
            entry_end=self.get_param("entry_end", None),  # type: ignore[arg-type]
        )
        if cfg.min_gap_pct <= 0:
            raise ValueError("min_gap_pct must be > 0")
        self._entry_start = None
        self._entry_end = None
        if cfg.entry_start is not None or cfg.entry_end is not None:
            if cfg.entry_start is None or cfg.entry_end is None:
                raise ValueError("entry_start and entry_end must both be set together")
            self._entry_start = _parse_hhmm(str(cfg.entry_start), field_name="entry_start")
            self._entry_end = _parse_hhmm(str(cfg.entry_end), field_name="entry_end")
            if self._entry_end <= self._entry_start:
                raise ValueError("entry_end must be after entry_start")
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
        now_t = _local_index(data, self.config.timezone)[-1].time()

        action = Signal.HOLD
        rationale = "no_gap_continuation"
        if (
            self._entry_start is not None
            and self._entry_end is not None
            and not _in_window(now_t, self._entry_start, self._entry_end)
        ):
            action = Signal.HOLD
            rationale = "outside_entry_window"
        elif gap_pct >= self.config.min_gap_pct and close_now > day_open:
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
                "entry_window_active": self._entry_start is not None and self._entry_end is not None,
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

