"""Codex intraday range-regime VWAP reversion strategy."""

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
class CodexIntradayRangeReversionConfig:
    timezone: str = "Asia/Kolkata"
    entry_start: str = "10:15"
    entry_end: str = "14:45"
    exit_time: str = "15:20"
    ema_fast_period: int = 15
    ema_slow_period: int = 45
    rsi_period: int = 10
    oversold_rsi: float = 30.0
    recovery_rsi: float = 52.0
    vwap_deviation_pct: float = 0.0055
    stop_deviation_pct: float = 0.011
    cross_count_lookback: int = 20
    min_vwap_crosses: int = 3
    trend_spread_max_pct: float = 0.003
    volume_lookback: int = 20
    max_volume_ratio: float = 1.8
    min_bars_in_session: int = 12


class CodexIntradayRangeReversionStrategy(BaseStrategy):
    """
    Mean-reversion strategy tuned for choppy/range intraday regimes.

    Long entries are allowed only when trend spread is compressed and
    VWAP cross-frequency signals two-sided market behavior.
    """

    config: CodexIntradayRangeReversionConfig
    _entry_start: time
    _entry_end: time
    _exit_time: time

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        cfg = CodexIntradayRangeReversionConfig(
            timezone=str(self.get_param("timezone", "Asia/Kolkata")),
            entry_start=str(self.get_param("entry_start", "10:15")),
            entry_end=str(self.get_param("entry_end", "14:45")),
            exit_time=str(self.get_param("exit_time", "15:20")),
            ema_fast_period=int(self.get_param("ema_fast_period", 15)),
            ema_slow_period=int(self.get_param("ema_slow_period", 45)),
            rsi_period=int(self.get_param("rsi_period", 10)),
            oversold_rsi=float(self.get_param("oversold_rsi", 30.0)),
            recovery_rsi=float(self.get_param("recovery_rsi", 52.0)),
            vwap_deviation_pct=float(self.get_param("vwap_deviation_pct", 0.0055)),
            stop_deviation_pct=float(self.get_param("stop_deviation_pct", 0.011)),
            cross_count_lookback=int(self.get_param("cross_count_lookback", 20)),
            min_vwap_crosses=int(self.get_param("min_vwap_crosses", 3)),
            trend_spread_max_pct=float(self.get_param("trend_spread_max_pct", 0.003)),
            volume_lookback=int(self.get_param("volume_lookback", 20)),
            max_volume_ratio=float(self.get_param("max_volume_ratio", 1.8)),
            min_bars_in_session=int(self.get_param("min_bars_in_session", 12)),
        )
        if cfg.ema_fast_period < 2 or cfg.ema_slow_period <= cfg.ema_fast_period:
            raise ValueError("Require ema_slow_period > ema_fast_period >= 2")
        if cfg.rsi_period < 2:
            raise ValueError("rsi_period must be >= 2")
        if not (0.0 <= cfg.oversold_rsi <= 100.0):
            raise ValueError("oversold_rsi must be in [0, 100]")
        if not (0.0 <= cfg.recovery_rsi <= 100.0):
            raise ValueError("recovery_rsi must be in [0, 100]")
        if cfg.recovery_rsi <= cfg.oversold_rsi:
            raise ValueError("recovery_rsi must be greater than oversold_rsi")
        if cfg.vwap_deviation_pct <= 0:
            raise ValueError("vwap_deviation_pct must be > 0")
        if cfg.stop_deviation_pct <= cfg.vwap_deviation_pct:
            raise ValueError("stop_deviation_pct must be > vwap_deviation_pct")
        if cfg.cross_count_lookback < 2:
            raise ValueError("cross_count_lookback must be >= 2")
        if cfg.min_vwap_crosses < 1:
            raise ValueError("min_vwap_crosses must be >= 1")
        if cfg.trend_spread_max_pct <= 0:
            raise ValueError("trend_spread_max_pct must be > 0")
        if cfg.volume_lookback < 2:
            raise ValueError("volume_lookback must be >= 2")
        if cfg.max_volume_ratio <= 0:
            raise ValueError("max_volume_ratio must be > 0")
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
        cfg = getattr(self, "config", CodexIntradayRangeReversionConfig())
        return (
            "CodexIntradayRangeReversion"
            f"({cfg.ema_fast_period},{cfg.ema_slow_period},{cfg.vwap_deviation_pct:.4f})"
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
            raise ValueError("CodexIntradayRangeReversionStrategy requires DatetimeIndex data")

        warmup = max(
            self.config.ema_slow_period,
            self.config.rsi_period,
            self.config.cross_count_lookback,
            self.config.volume_lookback,
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
        ema_fast = self.ema(close, self.config.ema_fast_period)
        ema_slow = self.ema(close, self.config.ema_slow_period)
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

        close_now = float(close.iloc[-1])
        close_prev = float(close.iloc[-2])
        diff = close - vwap
        crosses = ((diff * diff.shift(1)) < 0).astype(int)
        cross_count = int(crosses.tail(self.config.cross_count_lookback).sum())
        trend_spread_pct = abs(float(ema_fast_now) - float(ema_slow_now)) / close_now if close_now > 0 else 0.0
        range_regime = (
            trend_spread_pct <= self.config.trend_spread_max_pct
            and cross_count >= self.config.min_vwap_crosses
        )

        prev = data.iloc[:-1]
        avg_volume = float(prev["volume"].tail(self.config.volume_lookback).mean())
        current_volume = float(current_bar["volume"])
        volume_ratio = (current_volume / avg_volume) if avg_volume > 0 else 0.0

        now_t = local_idx[-1].time()
        in_entry_window = _in_window(now_t, self._entry_start, self._entry_end)

        deviation = (float(vwap_now) - close_now) / float(vwap_now) if float(vwap_now) != 0 else 0.0
        oversold_entry = (
            deviation >= self.config.vwap_deviation_pct
            and deviation < self.config.stop_deviation_pct
            and float(rsi_now) <= self.config.oversold_rsi
            and close_now > close_prev
            and volume_ratio <= self.config.max_volume_ratio
        )

        action = Signal.HOLD
        rationale = "no_setup"
        if now_t >= self._exit_time:
            action = Signal.EXIT
            rationale = "session_close_exit"
        elif in_entry_window and range_regime and oversold_entry:
            action = Signal.BUY
            rationale = "range_regime_vwap_reversion"
        elif (
            close_now >= float(vwap_now)
            or float(rsi_now) >= self.config.recovery_rsi
            or close_now <= float(vwap_now) * (1.0 - self.config.stop_deviation_pct)
        ):
            action = Signal.EXIT
            rationale = "reversion_exit_or_stop"

        confidence = 0.0
        if action == Signal.BUY:
            confidence = min(0.9, 0.55 + max(deviation * 30.0, 0.0))
        elif action == Signal.EXIT:
            confidence = 0.6

        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=confidence,
            rationale=rationale,
            tags=("intraday", "codex", "range", "mean_reversion"),
            metadata={
                "ema_fast": float(ema_fast_now),
                "ema_slow": float(ema_slow_now),
                "vwap": float(vwap_now),
                "rsi": float(rsi_now),
                "deviation": float(deviation),
                "trend_spread_pct": float(trend_spread_pct),
                "cross_count": cross_count,
                "range_regime": range_regime,
                "volume_ratio": float(volume_ratio),
                "in_entry_window": in_entry_window,
            },
        )

    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return self.generate_signal(data, current_bar, bar_index).action
