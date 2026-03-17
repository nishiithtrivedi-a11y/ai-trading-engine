"""
Technical Analysis Module.

Computes standard technical indicators by delegating to the existing
:class:`~src.strategies.base_strategy.BaseStrategy` static helper methods.
This ensures a single canonical implementation of RSI, SMA, EMA, ATR, etc.
across both the strategy layer and the analysis framework.

Features produced
-----------------
rsi_14           : RSI(14) value at the last bar (float | None)
sma_20           : SMA(20) at the last bar (float)
sma_50           : SMA(50) at the last bar (float)
ema_20           : EMA(20) at the last bar (float)
atr_14           : ATR(14) at the last bar (float | None)
donchian_high_20 : Donchian channel high(20) (float)
donchian_low_20  : Donchian channel low(20) (float)
trend_sma20_50   : "bullish" | "bearish" | "insufficient_data"
price_vs_sma20   : (close - SMA20) / SMA20  — normalised distance
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from src.analysis.base import BaseAnalysisModule


class TechnicalAnalysisModule(BaseAnalysisModule):
    """Technical indicator analysis module.

    Delegates all indicator computation to :class:`BaseStrategy` static
    methods to avoid duplicating indicator logic.
    """

    name: str = "technical"
    version: str = "1.0.0"

    def build_features(self, data: pd.DataFrame, context: dict) -> dict:
        """Compute technical indicators from the last bar of OHLCV data."""
        # Lazy import to avoid circular dependency at module load time
        from src.strategies.base_strategy import BaseStrategy

        if data is None or data.empty:
            return {}

        close = data["close"]
        features: dict = {}

        # RSI(14)
        if len(close) >= 14:
            try:
                rsi_series = BaseStrategy.rsi(close, period=14)
                rsi_val = rsi_series.iloc[-1]
                features["rsi_14"] = None if pd.isna(rsi_val) else float(rsi_val)
            except Exception:  # noqa: BLE001
                features["rsi_14"] = None

        # SMA(20) and SMA(50)
        if len(close) >= 20:
            features["sma_20"] = float(BaseStrategy.sma(close, 20).iloc[-1])
        if len(close) >= 50:
            features["sma_50"] = float(BaseStrategy.sma(close, 50).iloc[-1])

        # EMA(20)
        if len(close) >= 20:
            features["ema_20"] = float(BaseStrategy.ema(close, 20).iloc[-1])

        # ATR(14)
        if all(col in data.columns for col in ("high", "low")) and len(close) >= 14:
            try:
                atr_series = BaseStrategy.atr(data["high"], data["low"], close, period=14)
                atr_val = atr_series.iloc[-1]
                features["atr_14"] = None if pd.isna(atr_val) else float(atr_val)
            except Exception:  # noqa: BLE001
                features["atr_14"] = None

        # Donchian channels(20)
        if "high" in data.columns and len(data) >= 20:
            features["donchian_high_20"] = float(
                BaseStrategy.donchian_high(data["high"], 20).iloc[-1]
            )
        if "low" in data.columns and len(data) >= 20:
            features["donchian_low_20"] = float(
                BaseStrategy.donchian_low(data["low"], 20).iloc[-1]
            )

        # Trend state: SMA20 vs SMA50
        if len(close) >= 50:
            sma20 = float(BaseStrategy.sma(close, 20).iloc[-1])
            sma50 = float(BaseStrategy.sma(close, 50).iloc[-1])
            features["trend_sma20_50"] = "bullish" if sma20 > sma50 else "bearish"
        else:
            features["trend_sma20_50"] = "insufficient_data"

        # Normalised distance from SMA20
        if "sma_20" in features:
            sma20 = features["sma_20"]
            last_close = float(close.iloc[-1])
            features["price_vs_sma20"] = (
                (last_close - sma20) / sma20 if sma20 != 0 else None
            )

        return features

    def health_check(self) -> dict:
        return {
            "status": "ok",
            "module": self.name,
            "version": self.version,
            "description": "Technical indicators via BaseStrategy helpers",
        }
