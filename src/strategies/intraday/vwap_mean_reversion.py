"""VWAP mean-reversion strategy for intraday data."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal


@dataclass
class VWAPMeanReversionConfig:
    deviation_pct: float = 0.005
    timezone: str = "Asia/Kolkata"
    timestamp_col: str = "timestamp"


class VWAPMeanReversionStrategy(BaseStrategy):
    """Fade large deviations from intraday VWAP."""

    config: VWAPMeanReversionConfig

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        cfg = VWAPMeanReversionConfig(
            deviation_pct=float(self.get_param("deviation_pct", 0.005)),
            timezone=str(self.get_param("timezone", "Asia/Kolkata")),
            timestamp_col=str(self.get_param("timestamp_col", "timestamp")),
        )
        if cfg.deviation_pct <= 0:
            raise ValueError("deviation_pct must be > 0")
        self.config = cfg

    @property
    def name(self) -> str:
        cfg = getattr(self, "config", VWAPMeanReversionConfig())
        return f"VWAPMeanReversion({cfg.deviation_pct:.4f})"

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
        if len(data) < 5:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="insufficient_bars",
            )

        if isinstance(data.index, pd.DatetimeIndex):
            df = data.reset_index().rename(columns={data.index.name or "index": self.config.timestamp_col})
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
        if pd.isna(vwap_now):
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="vwap_unavailable",
            )

        close_now = float(current_bar["close"])
        upper = float(vwap_now) * (1.0 + self.config.deviation_pct)
        lower = float(vwap_now) * (1.0 - self.config.deviation_pct)

        action = Signal.HOLD
        rationale = "inside_vwap_band"
        if close_now > upper:
            action = Signal.SELL
            rationale = "mean_reversion_from_upper_vwap_band"
        elif close_now < lower:
            action = Signal.BUY
            rationale = "mean_reversion_from_lower_vwap_band"

        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=0.7 if action != Signal.HOLD else 0.0,
            rationale=rationale,
            tags=("intraday", "vwap", "mean_reversion"),
            metadata={
                "vwap": float(vwap_now),
                "upper_band": upper,
                "lower_band": lower,
                "deviation_pct": self.config.deviation_pct,
            },
        )

    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return self.generate_signal(data, current_bar, bar_index).action

