"""
Volatility regime detection.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.core.data_handler import DataHandler
from src.market_intelligence.config import VolatilityRegimeConfig
from src.market_intelligence.models import VolatilityRegimeSnapshot, VolatilityRegimeType
from src.strategies.base_strategy import BaseStrategy


class VolatilityRegimeError(Exception):
    """Raised when volatility regime detection fails."""


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, float(value)))


@dataclass
class VolatilityRegimeAnalyzer:
    def detect(
        self,
        symbol: str,
        data_handler: DataHandler,
        config: VolatilityRegimeConfig,
    ) -> VolatilityRegimeSnapshot:
        df = data_handler.data
        required = {"high", "low", "close"}
        if not required.issubset(set(df.columns)):
            raise VolatilityRegimeError(
                f"Missing required columns for volatility regime: {sorted(required - set(df.columns))}"
            )

        min_bars = max(config.atr_baseline_period, config.realized_vol_window) + 2
        if len(df) < min_bars:
            raise VolatilityRegimeError(
                f"Insufficient bars for volatility regime ({len(df)} < {min_bars})"
            )

        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)

        returns = close.pct_change().dropna()
        realized = float(returns.tail(config.realized_vol_window).std() * np.sqrt(252))

        atr_series = BaseStrategy.atr(high=high, low=low, close=close, period=config.atr_period)
        atr_latest = float(atr_series.iloc[-1]) if pd.notna(atr_series.iloc[-1]) else 0.0
        atr_baseline = float(atr_series.tail(config.atr_baseline_period).mean())
        atr_ratio = (atr_latest / atr_baseline) if atr_baseline > 0 else 0.0

        regime = self._classify(realized, atr_ratio, config)
        state_score = self._state_score(realized, atr_ratio, config)

        return VolatilityRegimeSnapshot(
            symbol=symbol,
            timeframe=config.timeframe,
            timestamp=pd.Timestamp(df.index[-1]),
            regime=regime,
            realized_volatility=realized,
            atr_value=atr_latest,
            atr_ratio=atr_ratio,
            state_score=state_score,
            metadata={"atr_baseline": atr_baseline},
        )

    @staticmethod
    def _classify(
        realized: float,
        atr_ratio: float,
        config: VolatilityRegimeConfig,
    ) -> VolatilityRegimeType:
        if atr_ratio <= config.contraction_atr_ratio and realized <= config.low_vol_threshold:
            return VolatilityRegimeType.CONTRACTION
        if realized >= config.high_vol_threshold:
            return VolatilityRegimeType.HIGH
        if atr_ratio >= config.expansion_atr_ratio and realized > config.low_vol_threshold:
            return VolatilityRegimeType.EXPANDING
        if realized <= config.low_vol_threshold:
            return VolatilityRegimeType.LOW
        if atr_ratio <= config.contraction_atr_ratio:
            return VolatilityRegimeType.CONTRACTION
        return VolatilityRegimeType.UNKNOWN

    @staticmethod
    def _state_score(
        realized: float,
        atr_ratio: float,
        config: VolatilityRegimeConfig,
    ) -> float:
        vol_component = 50.0
        if config.high_vol_threshold > config.low_vol_threshold:
            vol_component = (
                (realized - config.low_vol_threshold)
                / (config.high_vol_threshold - config.low_vol_threshold)
            ) * 100.0
        atr_component = (atr_ratio - 0.5) * 100.0
        return _clamp(0.6 * vol_component + 0.4 * atr_component)
