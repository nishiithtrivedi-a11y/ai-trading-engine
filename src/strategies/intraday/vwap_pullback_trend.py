"""VWAP pullback trend continuation strategy."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal


@dataclass
class VWAPPullbackTrendConfig:
    timezone: str = "Asia/Kolkata"
    timestamp_col: str = "timestamp"
    pullback_tolerance_pct: float = 0.002
    direction: str = "long"  # long | short | both


class VWAPPullbackTrendStrategy(BaseStrategy):
    """
    Trade intraday pullbacks to VWAP in trend direction.

    Long setup:
    - Current close is above VWAP (uptrend context).
    - Prior close was near/below VWAP.
    - Current close reclaims above prior close.

    Short setup mirrors the same logic below VWAP.
    """

    config: VWAPPullbackTrendConfig

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        cfg = VWAPPullbackTrendConfig(
            timezone=str(self.get_param("timezone", "Asia/Kolkata")),
            timestamp_col=str(self.get_param("timestamp_col", "timestamp")),
            pullback_tolerance_pct=float(self.get_param("pullback_tolerance_pct", 0.002)),
            direction=str(self.get_param("direction", "long")).strip().lower(),
        )
        if cfg.pullback_tolerance_pct < 0:
            raise ValueError("pullback_tolerance_pct must be >= 0")
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

        self.require_columns(data, ["close", "volume"])
        if len(data) < 8:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="insufficient_bars",
            )

        if isinstance(data.index, pd.DatetimeIndex):
            df = data.reset_index().rename(
                columns={data.index.name or "index": self.config.timestamp_col}
            )
        else:
            self.require_columns(data, [self.config.timestamp_col])
            df = data.copy()

        vwap = self.vwap(
            df,
            price_col="close",
            volume_col="volume",
            timestamp_col=self.config.timestamp_col,
            timezone=self.config.timezone,
        )
        vwap_now = vwap.iloc[-1]
        vwap_prev = vwap.iloc[-2]
        if pd.isna(vwap_now) or pd.isna(vwap_prev):
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="vwap_unavailable",
            )

        close = data["close"].astype(float)
        close_now = float(close.iloc[-1])
        close_prev = float(close.iloc[-2])
        v_now = float(vwap_now)
        v_prev = float(vwap_prev)
        tol = self.config.pullback_tolerance_pct

        long_pullback = close_prev <= v_prev * (1.0 + tol)
        short_pullback = close_prev >= v_prev * (1.0 - tol)

        action = Signal.HOLD
        rationale = "no_vwap_pullback_setup"
        if (
            self.config.direction in {"long", "both"}
            and close_now > v_now
            and long_pullback
            and close_now > close_prev
        ):
            action = Signal.BUY
            rationale = "vwap_pullback_long_continuation"
        elif (
            self.config.direction in {"short", "both"}
            and close_now < v_now
            and short_pullback
            and close_now < close_prev
        ):
            action = Signal.SELL
            rationale = "vwap_breakdown_retest_short"

        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=0.72 if action != Signal.HOLD else 0.0,
            rationale=rationale,
            tags=("intraday", "vwap", "trend_pullback"),
            metadata={
                "vwap": v_now,
                "vwap_prev": v_prev,
                "pullback_tolerance_pct": self.config.pullback_tolerance_pct,
                "direction": self.config.direction,
            },
        )

    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return self.generate_signal(data, current_bar, bar_index).action

