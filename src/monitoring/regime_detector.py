"""
Market regime detection for Phase 4 monitoring.

Deterministic and threshold-driven; no hidden ML behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from src.core.data_handler import DataHandler
from src.monitoring.config import RegimeDetectorConfig
from src.monitoring.models import RegimeAssessment, RegimeState
from src.scanners.data_gateway import DataGateway


class RegimeDetectorError(Exception):
    """Raised when regime detection cannot be completed."""


@dataclass
class RegimeDetector:
    def detect(
        self,
        data_handler: DataHandler,
        config: RegimeDetectorConfig,
        label: Optional[str] = None,
    ) -> RegimeAssessment:
        if len(data_handler) < max(config.trend_slow_period, config.volatility_period) + 1:
            return RegimeAssessment(
                regime=RegimeState.UNKNOWN,
                reason="insufficient_data",
                metadata={
                    "label": label,
                    "bars_available": len(data_handler),
                    "min_required": max(config.trend_slow_period, config.volatility_period) + 1,
                },
            )

        close = data_handler.data["close"].astype(float)
        high = data_handler.data["high"].astype(float)
        low = data_handler.data["low"].astype(float)

        fast = close.rolling(config.trend_fast_period, min_periods=config.trend_fast_period).mean().iloc[-1]
        slow = close.rolling(config.trend_slow_period, min_periods=config.trend_slow_period).mean().iloc[-1]
        last_close = float(close.iloc[-1])

        if pd.isna(fast) or pd.isna(slow) or slow == 0:
            return RegimeAssessment(
                regime=RegimeState.UNKNOWN,
                reason="invalid_trend_inputs",
                metadata={"label": label},
            )

        trend_score = float((fast - slow) / slow)

        returns = close.pct_change().dropna()
        recent_returns = returns.tail(config.volatility_period)
        volatility = float(recent_returns.std()) if len(recent_returns) > 1 else 0.0

        lookback = max(config.volatility_period, 5)
        rolling_high = float(high.tail(lookback).max())
        rolling_low = float(low.tail(lookback).min())
        range_width = (rolling_high - rolling_low) / max(last_close, 1e-9)

        regime = self._classify_regime(
            trend_score=trend_score,
            volatility=volatility,
            range_width=range_width,
            close=last_close,
            fast=fast,
            slow=slow,
            config=config,
        )

        reason = (
            f"trend={trend_score:.4f}, volatility={volatility:.4f}, range_width={range_width:.4f}, "
            f"close={last_close:.2f}, fast={float(fast):.2f}, slow={float(slow):.2f}"
        )

        return RegimeAssessment(
            regime=regime,
            trend_score=trend_score,
            volatility_score=volatility,
            range_score=float(range_width),
            reason=reason,
            metadata={"label": label},
        )

    def detect_from_gateway(
        self,
        symbol: str,
        data_gateway: DataGateway,
        config: RegimeDetectorConfig,
    ) -> RegimeAssessment:
        timeframe = config.timeframe

        if config.use_benchmark and config.benchmark_symbol:
            try:
                benchmark_data = data_gateway.load_data(config.benchmark_symbol, timeframe)
                assessment = self.detect(
                    data_handler=benchmark_data,
                    config=config,
                    label=config.benchmark_symbol,
                )
                assessment.metadata["based_on"] = "benchmark"
                return assessment
            except Exception as exc:  # noqa: BLE001
                if not config.fallback_to_symbol:
                    raise RegimeDetectorError(
                        f"Benchmark regime detection failed for {config.benchmark_symbol}: {exc}"
                    ) from exc

                symbol_data = data_gateway.load_data(symbol, timeframe)
                assessment = self.detect(data_handler=symbol_data, config=config, label=symbol)
                assessment.metadata["based_on"] = "symbol_fallback"
                assessment.metadata["benchmark_error"] = str(exc)
                return assessment

        symbol_data = data_gateway.load_data(symbol, timeframe)
        assessment = self.detect(data_handler=symbol_data, config=config, label=symbol)
        assessment.metadata["based_on"] = "symbol"
        return assessment

    @staticmethod
    def _classify_regime(
        trend_score: float,
        volatility: float,
        range_width: float,
        close: float,
        fast: float,
        slow: float,
        config: RegimeDetectorConfig,
    ) -> RegimeState:
        if volatility >= config.high_volatility_threshold:
            return RegimeState.HIGH_VOLATILITY

        if volatility <= config.low_volatility_threshold:
            # Low vol may still be bullish/bearish if trend is clear.
            if trend_score > config.bullish_slope_threshold and close > fast > slow:
                return RegimeState.BULLISH
            if trend_score < -abs(config.bearish_slope_threshold) and close < fast < slow:
                return RegimeState.BEARISH
            return RegimeState.LOW_VOLATILITY

        if trend_score > config.bullish_slope_threshold and close > fast > slow:
            return RegimeState.BULLISH

        if trend_score < -abs(config.bearish_slope_threshold) and close < fast < slow:
            return RegimeState.BEARISH

        if range_width <= config.rangebound_width_threshold:
            return RegimeState.RANGEBOUND

        return RegimeState.UNKNOWN
