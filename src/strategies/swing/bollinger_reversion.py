"""Bollinger-band mean reversion strategy."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal
from src.strategies.common import bollinger_bands


@dataclass
class BollingerReversionConfig:
    window: int = 20
    num_std: float = 2.0


class BollingerReversionStrategy(BaseStrategy):
    """Buy lower-band extremes and fade upper-band extremes."""

    config: BollingerReversionConfig

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        cfg = BollingerReversionConfig(
            window=int(self.get_param("window", 20)),
            num_std=float(self.get_param("num_std", 2.0)),
        )
        if cfg.window < 5:
            raise ValueError("window must be >= 5")
        if cfg.num_std <= 0:
            raise ValueError("num_std must be > 0")
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
        self.require_columns(data, ["close"])
        if len(data) < self.config.window + 1:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="insufficient_bars",
            )

        close = data["close"].astype(float)
        middle, upper, lower = bollinger_bands(
            close,
            window=self.config.window,
            num_std=self.config.num_std,
        )

        close_now = float(close.iloc[-1])
        middle_now = middle.iloc[-1]
        upper_now = upper.iloc[-1]
        lower_now = lower.iloc[-1]

        if pd.isna(middle_now) or pd.isna(upper_now) or pd.isna(lower_now):
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="indicator_warmup",
            )

        action = Signal.HOLD
        rationale = "inside_bands"
        if close_now < float(lower_now):
            action = Signal.BUY
            rationale = "lower_band_reversion"
        elif close_now > float(upper_now):
            action = Signal.SELL
            rationale = "upper_band_reversion"
        elif close_now >= float(middle_now):
            action = Signal.EXIT
            rationale = "reverted_to_mean"

        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=0.7 if action != Signal.HOLD else 0.0,
            rationale=rationale,
            tags=("swing", "mean_reversion", "bollinger"),
            metadata={
                "middle_band": float(middle_now),
                "upper_band": float(upper_now),
                "lower_band": float(lower_now),
            },
        )

    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return self.generate_signal(data, current_bar, bar_index).action

