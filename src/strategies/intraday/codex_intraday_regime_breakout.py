"""Codex intraday regime-gated volatility-compression breakout strategy."""

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
class CodexIntradayRegimeBreakoutConfig:
    timezone: str = "Asia/Kolkata"
    entry_start: str = "10:00"
    entry_end: str = "14:50"
    exit_time: str = "15:20"
    fast_ema_period: int = 21
    slow_ema_period: int = 55
    atr_period: int = 14
    compression_lookback: int = 12
    compression_threshold_pct: float = 0.006
    breakout_buffer_pct: float = 0.0008
    volume_lookback: int = 20
    volume_multiplier: float = 1.25
    min_trend_strength: float = 0.35
    min_bars_in_session: int = 9


class CodexIntradayRegimeBreakoutStrategy(BaseStrategy):
    """
    Trade upside breakouts only when the market is both:
    1) internally trending, and
    2) emerging from short-term volatility compression.

    Signals are advisory-only and execution-disabled by engine design.
    """

    config: CodexIntradayRegimeBreakoutConfig
    _entry_start: time
    _entry_end: time
    _exit_time: time

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        cfg = CodexIntradayRegimeBreakoutConfig(
            timezone=str(self.get_param("timezone", "Asia/Kolkata")),
            entry_start=str(self.get_param("entry_start", "10:00")),
            entry_end=str(self.get_param("entry_end", "14:50")),
            exit_time=str(self.get_param("exit_time", "15:20")),
            fast_ema_period=int(self.get_param("fast_ema_period", 21)),
            slow_ema_period=int(self.get_param("slow_ema_period", 55)),
            atr_period=int(self.get_param("atr_period", 14)),
            compression_lookback=int(self.get_param("compression_lookback", 12)),
            compression_threshold_pct=float(self.get_param("compression_threshold_pct", 0.006)),
            breakout_buffer_pct=float(self.get_param("breakout_buffer_pct", 0.0008)),
            volume_lookback=int(self.get_param("volume_lookback", 20)),
            volume_multiplier=float(self.get_param("volume_multiplier", 1.25)),
            min_trend_strength=float(self.get_param("min_trend_strength", 0.35)),
            min_bars_in_session=int(self.get_param("min_bars_in_session", 9)),
        )
        if cfg.fast_ema_period < 2 or cfg.slow_ema_period <= cfg.fast_ema_period:
            raise ValueError("Require slow_ema_period > fast_ema_period >= 2")
        if cfg.atr_period < 2:
            raise ValueError("atr_period must be >= 2")
        if cfg.compression_lookback < 3:
            raise ValueError("compression_lookback must be >= 3")
        if cfg.compression_threshold_pct <= 0:
            raise ValueError("compression_threshold_pct must be > 0")
        if cfg.breakout_buffer_pct < 0:
            raise ValueError("breakout_buffer_pct must be >= 0")
        if cfg.volume_lookback < 2:
            raise ValueError("volume_lookback must be >= 2")
        if cfg.volume_multiplier <= 0:
            raise ValueError("volume_multiplier must be > 0")
        if cfg.min_trend_strength <= 0:
            raise ValueError("min_trend_strength must be > 0")
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
        cfg = getattr(self, "config", CodexIntradayRegimeBreakoutConfig())
        return (
            "CodexIntradayRegimeBreakout"
            f"({cfg.fast_ema_period},{cfg.slow_ema_period},{cfg.compression_lookback})"
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
            raise ValueError("CodexIntradayRegimeBreakoutStrategy requires DatetimeIndex data")

        warmup = max(
            self.config.slow_ema_period,
            self.config.atr_period,
            self.config.volume_lookback,
            self.config.compression_lookback,
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
        low = data["low"].astype(float)

        ema_fast = self.ema(close, self.config.fast_ema_period)
        ema_slow = self.ema(close, self.config.slow_ema_period)
        atr = self.atr(high, low, close, self.config.atr_period)
        vwap = self._vwap_series(data)

        ema_fast_now = ema_fast.iloc[-1]
        ema_slow_now = ema_slow.iloc[-1]
        atr_now = atr.iloc[-1]
        vwap_now = vwap.iloc[-1]
        if pd.isna(ema_fast_now) or pd.isna(ema_slow_now) or pd.isna(atr_now) or pd.isna(vwap_now):
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                rationale="indicator_warmup",
            )

        close_now = float(close.iloc[-1])
        trend_strength = 0.0
        if float(atr_now) > 0:
            trend_strength = abs(float(ema_fast_now) - float(ema_slow_now)) / float(atr_now)

        trend_regime = (
            close_now > float(vwap_now)
            and close_now > float(ema_fast_now)
            and float(ema_fast_now) > float(ema_slow_now)
            and trend_strength >= self.config.min_trend_strength
        )

        prev = data.iloc[:-1]
        if len(prev) < self.config.compression_lookback:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                rationale="insufficient_breakout_context",
            )

        compression_slice = prev.tail(self.config.compression_lookback)
        range_high = float(compression_slice["high"].max())
        range_low = float(compression_slice["low"].min())
        prev_close = float(prev["close"].iloc[-1])
        compression_pct = ((range_high - range_low) / prev_close) if prev_close > 0 else 0.0
        is_compressed = compression_pct <= self.config.compression_threshold_pct

        avg_volume = float(prev["volume"].tail(self.config.volume_lookback).mean())
        current_volume = float(current_bar["volume"])
        volume_ratio = (current_volume / avg_volume) if avg_volume > 0 else 0.0

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
            and is_compressed
            and volume_ratio >= self.config.volume_multiplier
            and close_now > range_high * (1.0 + self.config.breakout_buffer_pct)
        ):
            action = Signal.BUY
            rationale = "regime_compression_breakout"
        elif close_now < min(float(ema_fast_now), float(vwap_now)):
            action = Signal.EXIT
            rationale = "trend_break_exit"

        confidence = 0.0
        if action == Signal.BUY:
            confidence = min(0.9, 0.55 + 0.18 * volume_ratio + 0.15 * trend_strength)
        elif action == Signal.EXIT:
            confidence = 0.65

        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=confidence,
            rationale=rationale,
            tags=("intraday", "codex", "regime", "breakout"),
            metadata={
                "ema_fast": float(ema_fast_now),
                "ema_slow": float(ema_slow_now),
                "vwap": float(vwap_now),
                "atr": float(atr_now),
                "trend_strength": float(trend_strength),
                "compression_pct": float(compression_pct),
                "volume_ratio": float(volume_ratio),
                "range_high": range_high,
                "range_low": range_low,
                "in_entry_window": in_entry_window,
            },
        )

    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return self.generate_signal(data, current_bar, bar_index).action
