"""Limited pair-spread z-score strategy."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal
from src.strategies.common import rolling_zscore


@dataclass
class PairsZScoreConfig:
    pair_close_col: str = "pair_close"
    lookback: int = 60
    hedge_ratio: float = 1.0
    entry_z: float = 2.0
    exit_z: float = 0.5


class PairsZScoreStrategy(BaseStrategy):
    """
    Simplified pair-spread reversion strategy.

    Limitation:
    - Requires a pre-aligned secondary series in `pair_close_col`.
    - Does not estimate dynamic hedge ratios or transaction-cost model.
    """

    config: PairsZScoreConfig

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        cfg = PairsZScoreConfig(
            pair_close_col=str(self.get_param("pair_close_col", "pair_close")),
            lookback=int(self.get_param("lookback", 60)),
            hedge_ratio=float(self.get_param("hedge_ratio", 1.0)),
            entry_z=float(self.get_param("entry_z", 2.0)),
            exit_z=float(self.get_param("exit_z", 0.5)),
        )
        if cfg.lookback < 10:
            raise ValueError("lookback must be >= 10")
        if cfg.entry_z <= 0 or cfg.exit_z < 0:
            raise ValueError("entry_z must be > 0 and exit_z must be >= 0")
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
        self.require_columns(data, ["close", self.config.pair_close_col])
        if len(data) < self.config.lookback + 2:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="insufficient_bars",
            )

        close = data["close"].astype(float)
        pair_close = data[self.config.pair_close_col].astype(float)

        spread = close - self.config.hedge_ratio * pair_close
        z = rolling_zscore(spread, self.config.lookback)
        z_now = z.iloc[-1]
        if pd.isna(z_now):
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="zscore_unavailable",
            )

        action = Signal.HOLD
        rationale = "spread_neutral"
        if float(z_now) >= self.config.entry_z:
            action = Signal.SELL
            rationale = "spread_rich_short_primary"
        elif float(z_now) <= -self.config.entry_z:
            action = Signal.BUY
            rationale = "spread_cheap_long_primary"
        elif abs(float(z_now)) <= self.config.exit_z:
            action = Signal.EXIT
            rationale = "spread_reverted_exit"

        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=0.7 if action != Signal.HOLD else 0.0,
            rationale=rationale,
            tags=("quant", "pairs", "mean_reversion", "limited"),
            metadata={
                "zscore": float(z_now),
                "entry_z": self.config.entry_z,
                "exit_z": self.config.exit_z,
                "pair_close_col": self.config.pair_close_col,
            },
        )

    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return self.generate_signal(data, current_bar, bar_index).action

