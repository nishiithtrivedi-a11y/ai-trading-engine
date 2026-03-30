"""Codex intraday trend pullback-and-reentry strategy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal


def _parse_hhmm(value: str, *, field_name: str) -> time:
    clean = str(value).strip()
    try:
        parsed = pd.to_datetime(clean, format="%H:%M")
    except ValueError as exc:
        raise ValueError(f"{field_name} must be HH:MM (24-hour) format") from exc
    return parsed.time()


def _in_window(now: time, start: time, end: time) -> bool:
    return start <= now <= end


@dataclass
class CodexIntradayTrendReentryConfig:
    timezone: str = "Asia/Kolkata"
    entry_start: str = "09:35"
    entry_end: str = "14:40"
    exit_time: str = "15:20"
    fast_ema_period: int = 20
    slow_ema_period: int = 50
    slope_lookback: int = 6
    pullback_lookback: int = 6
    pullback_tolerance_pct: float = 0.0035
    trigger_buffer_pct: float = 0.0005
    rsi_period: int = 14
    rsi_floor: float = 45.0
    volume_lookback: int = 20
    min_volume_ratio: float = 0.9
    min_bars_in_session: int = 8


class CodexIntradayTrendReentryStrategy(BaseStrategy):
    """
    Capture trend continuation after shallow pullbacks to VWAP/EMA support.

    Long bias only:
    - Regime: EMA trend + positive slow EMA slope + RSI strength
    - Setup: recent pullback toward dynamic support
    - Trigger: momentum reclaim above prior high
    """

    config: CodexIntradayTrendReentryConfig
    _entry_start: time
    _entry_end: time
    _exit_time: time

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        cfg = CodexIntradayTrendReentryConfig(
            timezone=str(self.get_param("timezone", "Asia/Kolkata")),
            entry_start=str(self.get_param("entry_start", "09:35")),
            entry_end=str(self.get_param("entry_end", "14:40")),
            exit_time=str(self.get_param("exit_time", "15:20")),
            fast_ema_period=int(self.get_param("fast_ema_period", 20)),
            slow_ema_period=int(self.get_param("slow_ema_period", 50)),
            slope_lookback=int(self.get_param("slope_lookback", 6)),
            pullback_lookback=int(self.get_param("pullback_lookback", 6)),
            pullback_tolerance_pct=float(self.get_param("pullback_tolerance_pct", 0.0035)),
            trigger_buffer_pct=float(self.get_param("trigger_buffer_pct", 0.0005)),
            rsi_period=int(self.get_param("rsi_period", 14)),
            rsi_floor=float(self.get_param("rsi_floor", 45.0)),
            volume_lookback=int(self.get_param("volume_lookback", 20)),
            min_volume_ratio=float(self.get_param("min_volume_ratio", 0.9)),
            min_bars_in_session=int(self.get_param("min_bars_in_session", 8)),
        )
        if cfg.fast_ema_period < 2 or cfg.slow_ema_period <= cfg.fast_ema_period:
            raise ValueError("Require slow_ema_period > fast_ema_period >= 2")
        if cfg.slope_lookback < 1:
            raise ValueError("slope_lookback must be >= 1")
        if cfg.pullback_lookback < 2:
            raise ValueError("pullback_lookback must be >= 2")
        if cfg.pullback_tolerance_pct < 0:
            raise ValueError("pullback_tolerance_pct must be >= 0")
        if cfg.trigger_buffer_pct < 0:
            raise ValueError("trigger_buffer_pct must be >= 0")
        if cfg.rsi_period < 2:
            raise ValueError("rsi_period must be >= 2")
        if not (0.0 <= cfg.rsi_floor <= 100.0):
            raise ValueError("rsi_floor must be in [0, 100]")
        if cfg.volume_lookback < 2:
            raise ValueError("volume_lookback must be >= 2")
        if cfg.min_volume_ratio <= 0:
            raise ValueError("min_volume_ratio must be > 0")
        if cfg.min_bars_in_session < 3:
            raise ValueError("min_bars_in_session must be >= 3")

        self._entry_start = _parse_hhmm(cfg.entry_start, field_name="entry_start")
        self._entry_end = _parse_hhmm(cfg.entry_end, field_name="entry_end")
        self._exit_time = _parse_hhmm(cfg.exit_time, field_name="exit_time")
        if self._entry_end <= self._entry_start:
            raise ValueError("entry_end must be after entry_start")
        if self._exit_time <= self._entry_end:
            raise ValueError("exit_time must be after entry_end")
        self.config = cfg

    @property
    def name(self) -> str:
        cfg = getattr(self, "config", CodexIntradayTrendReentryConfig())
        return (
            "CodexIntradayTrendReentry"
            f"({cfg.fast_ema_period},{cfg.slow_ema_period},{cfg.pullback_lookback})"
        )

    def _vwap_series(self, data: pd.DataFrame) -> pd.Series:
        frame = data.copy()
        if isinstance(data.index, pd.DatetimeIndex):
            frame["timestamp"] = data.index
        else:
            self.require_columns(frame, ["timestamp"])
        return self.vwap(
            frame,
            price_col="close",
            volume_col="volume",
            timestamp_col="timestamp",
            timezone=self.config.timezone,
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

        self.require_columns(data, ["high", "low", "close", "volume"])
        if not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError("CodexIntradayTrendReentryStrategy requires DatetimeIndex data")

        warmup = max(
            self.config.slow_ema_period + self.config.slope_lookback,
            self.config.rsi_period,
            self.config.volume_lookback,
            self.config.pullback_lookback,
        ) + 2
        if len(data) < warmup:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                rationale="insufficient_bars",
            )

        idx = data.index
        if "_cached_local_ts" in data.columns:
            local_idx = pd.DatetimeIndex(pd.to_datetime(data["_cached_local_ts"]))
        elif idx.tz is None:
            local_idx = idx.tz_localize("UTC").tz_convert(self.config.timezone)
        else:
            local_idx = idx.tz_convert(self.config.timezone)

        day_keys = pd.Series(local_idx.date, index=data.index)
        today = day_keys.iloc[-1]
        session_bars = int((day_keys == today).sum())
        if session_bars < self.config.min_bars_in_session:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                rationale="session_warmup",
            )

        close = data["close"].astype(float)
        high = data["high"].astype(float)

        ema_fast = self.ema(close, self.config.fast_ema_period)
        ema_slow = self.ema(close, self.config.slow_ema_period)
        rsi = self.rsi(close, self.config.rsi_period)
        vwap = self._vwap_series(data)

        ema_fast_now = ema_fast.iloc[-1]
        ema_slow_now = ema_slow.iloc[-1]
        rsi_now = rsi.iloc[-1]
        vwap_now = vwap.iloc[-1]
        if pd.isna(ema_fast_now) or pd.isna(ema_slow_now) or pd.isna(rsi_now) or pd.isna(vwap_now):
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                rationale="indicator_warmup",
            )

        slope_ref = ema_slow.iloc[-1 - self.config.slope_lookback]
        if pd.isna(slope_ref):
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                rationale="slope_warmup",
            )
        slow_slope = float(ema_slow_now) - float(slope_ref)

        close_now = float(close.iloc[-1])
        prev = data.iloc[:-1]
        if len(prev) < self.config.pullback_lookback:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                rationale="insufficient_pullback_context",
            )

        support_ref = max(float(vwap_now), float(ema_fast_now))
        recent_pullback_low = float(prev["low"].tail(self.config.pullback_lookback).min())
        pullback_seen = recent_pullback_low <= support_ref * (1.0 + self.config.pullback_tolerance_pct)
        trigger_level = float(high.iloc[-2]) * (1.0 + self.config.trigger_buffer_pct)

        avg_volume = float(prev["volume"].tail(self.config.volume_lookback).mean())
        current_volume = float(current_bar["volume"])
        volume_ratio = (current_volume / avg_volume) if avg_volume > 0 else 0.0

        trend_regime = (
            close_now > float(vwap_now)
            and close_now > float(ema_fast_now)
            and float(ema_fast_now) > float(ema_slow_now)
            and slow_slope > 0
            and float(rsi_now) >= self.config.rsi_floor
        )

        now_t = local_idx[-1].time()
        in_entry_window = _in_window(now_t, self._entry_start, self._entry_end)

        action = Signal.HOLD
        rationale = "no_setup"
        if now_t >= self._exit_time:
            action = Signal.EXIT
            rationale = "session_close_exit"
        elif (
            in_entry_window
            and trend_regime
            and pullback_seen
            and volume_ratio >= self.config.min_volume_ratio
            and close_now > trigger_level
        ):
            action = Signal.BUY
            rationale = "trend_pullback_reentry"
        elif (
            close_now < float(ema_slow_now)
            or close_now < float(vwap_now) * (1.0 - self.config.pullback_tolerance_pct)
            or float(rsi_now) < max(20.0, self.config.rsi_floor - 8.0)
        ):
            action = Signal.EXIT
            rationale = "trend_failure_exit"

        confidence = 0.0
        if action == Signal.BUY:
            confidence = min(0.9, 0.58 + 0.2 * volume_ratio + 0.001 * max(float(rsi_now) - 40.0, 0.0))
        elif action == Signal.EXIT:
            confidence = 0.62

        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=confidence,
            rationale=rationale,
            tags=("intraday", "codex", "trend", "pullback"),
            metadata={
                "ema_fast": float(ema_fast_now),
                "ema_slow": float(ema_slow_now),
                "vwap": float(vwap_now),
                "rsi": float(rsi_now),
                "slow_slope": float(slow_slope),
                "pullback_low": recent_pullback_low,
                "support_ref": support_ref,
                "trigger_level": trigger_level,
                "volume_ratio": float(volume_ratio),
                "in_entry_window": in_entry_window,
            },
        )

    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return self.generate_signal(data, current_bar, bar_index).action
