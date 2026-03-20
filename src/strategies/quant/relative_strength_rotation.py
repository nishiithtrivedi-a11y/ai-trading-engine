"""Limited relative-strength rotation proxy."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal


@dataclass
class RelativeStrengthRotationConfig:
    benchmark_col: str = "benchmark_close"
    rs_lookback: int = 60
    rs_ma_period: int = 20


class RelativeStrengthRotationStrategy(BaseStrategy):
    """
    Simplified relative-strength signal.

    Limitation:
    - Requires a benchmark series in `benchmark_col` aligned to the same bars.
    - Single-asset strategy output; true rotation/allocation remains portfolio-layer.
    """

    config: RelativeStrengthRotationConfig

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        cfg = RelativeStrengthRotationConfig(
            benchmark_col=str(self.get_param("benchmark_col", "benchmark_close")),
            rs_lookback=int(self.get_param("rs_lookback", 60)),
            rs_ma_period=int(self.get_param("rs_ma_period", 20)),
        )
        if cfg.rs_lookback < 10 or cfg.rs_ma_period < 5:
            raise ValueError("rs_lookback must be >= 10 and rs_ma_period >= 5")
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
        self.require_columns(data, ["close", self.config.benchmark_col])
        min_bars = max(self.config.rs_lookback, self.config.rs_ma_period) + 2
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
        benchmark = data[self.config.benchmark_col].astype(float)
        rs = close / benchmark.replace(0.0, pd.NA)
        rs_now = rs.iloc[-1]
        rs_prev = rs.iloc[-(self.config.rs_lookback + 1)]
        rs_ma = self.sma(rs, self.config.rs_ma_period).iloc[-1]
        if pd.isna(rs_now) or pd.isna(rs_prev) or pd.isna(rs_ma):
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="relative_strength_unavailable",
            )

        rs_momentum = (float(rs_now) - float(rs_prev)) / abs(float(rs_prev)) if float(rs_prev) != 0 else 0.0
        action = Signal.HOLD
        rationale = "neutral_relative_strength"
        if float(rs_now) > float(rs_ma) and rs_momentum > 0:
            action = Signal.BUY
            rationale = "relative_strength_leader"
        elif float(rs_now) < float(rs_ma) and rs_momentum < 0:
            action = Signal.EXIT
            rationale = "relative_strength_deterioration"

        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=0.7 if action != Signal.HOLD else 0.0,
            rationale=rationale,
            tags=("quant", "relative_strength", "limited"),
            metadata={
                "relative_strength": float(rs_now),
                "relative_strength_ma": float(rs_ma),
                "relative_strength_momentum": float(rs_momentum),
                "benchmark_col": self.config.benchmark_col,
            },
        )

    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return self.generate_signal(data, current_bar, bar_index).action

