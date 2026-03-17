"""
Opportunity scoring and ranking.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import pandas as pd

from src.core.data_handler import DataHandler
from src.scanners.config import ScannerConfig
from src.scanners.models import Opportunity, SignalSnapshot, TradeSetup
from src.strategies.base_strategy import BaseStrategy

if TYPE_CHECKING:
    from src.analysis.registry import AnalysisRegistry


class OpportunityScorerError(Exception):
    """Raised when an opportunity score cannot be computed."""


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


@dataclass
class OpportunityScorer:
    rr_cap: float = 3.0
    trend_fast_period: int = 20
    trend_slow_period: int = 50
    freshness_decay_bars: int = 20

    def score(
        self,
        signal: SignalSnapshot,
        setup: TradeSetup,
        data_handler: DataHandler,
        scanner_config: ScannerConfig,
        analysis_registry: Optional["AnalysisRegistry"] = None,
    ) -> dict[str, float]:
        if not signal.is_actionable:
            raise OpportunityScorerError("Cannot score a non-actionable signal")

        components = {
            "signal": self._signal_component(signal, data_handler),
            "risk_reward": self._risk_reward_component(setup),
            "trend": self._trend_component(data_handler),
            "liquidity": self._liquidity_component(data_handler),
            "freshness": self._freshness_component(signal, data_handler),
        }

        weights = scanner_config.score_weights
        weighted_sum = 0.0
        total_weight = 0.0

        for key, value in components.items():
            w = float(weights.get(key, 0.0))
            if w <= 0:
                continue
            weighted_sum += w * _clamp(value)
            total_weight += w

        if total_weight <= 0:
            raise OpportunityScorerError("score_weights produced zero effective weight")

        final_score = _clamp(weighted_sum / total_weight, 0.0, 1.0) * 100.0

        result: dict[str, float] = {
            "score": final_score,
            "signal": _clamp(components["signal"]),
            "risk_reward": _clamp(components["risk_reward"]),
            "trend": _clamp(components["trend"]),
            "liquidity": _clamp(components["liquidity"]),
            "freshness": _clamp(components["freshness"]),
        }

        if analysis_registry is not None:
            try:
                from src.analysis.feature_schema import FeatureOutput  # noqa: PLC0415

                features = FeatureOutput.from_modules(
                    analysis_registry.enabled_modules(),
                    data_handler.data,
                    {"signal": signal, "setup": setup},
                )
                result["analysis_features"] = features.to_dict()  # type: ignore[assignment]
            except Exception:  # noqa: BLE001
                result["analysis_features"] = {}  # type: ignore[assignment]

        return result

    @staticmethod
    def rank(opportunities: list[Opportunity]) -> list[Opportunity]:
        ranked = sorted(opportunities, key=lambda o: float(o.score), reverse=True)
        for idx, opp in enumerate(ranked, start=1):
            opp.rank = idx
        return ranked

    def _signal_component(self, signal: SignalSnapshot, data_handler: DataHandler) -> float:
        if not signal.is_actionable:
            return 0.0

        strategy_name = signal.strategy_name
        if strategy_name == "RSIReversionStrategy":
            return self._signal_rsi_component(signal, data_handler)
        if strategy_name == "SMACrossoverStrategy":
            return self._signal_sma_component(signal, data_handler)

        if "confidence" in signal.extras:
            return _clamp(float(signal.extras["confidence"]))
        return 1.0 if signal.signal == "buy" else 0.5

    @staticmethod
    def _signal_rsi_component(signal: SignalSnapshot, data_handler: DataHandler) -> float:
        oversold = float(signal.strategy_params.get("oversold", signal.extras.get("oversold_threshold", 30.0)))
        period = int(signal.strategy_params.get("rsi_period", 14))

        rsi_now = signal.extras.get("rsi_current")
        rsi_slope = signal.extras.get("rsi_slope")

        if rsi_now is None:
            rsi_series = BaseStrategy.rsi(data_handler.data["close"], period)
            if len(rsi_series) > 0 and pd.notna(rsi_series.iloc[-1]):
                rsi_now = float(rsi_series.iloc[-1])
            if len(rsi_series) > 1 and pd.notna(rsi_series.iloc[-2]) and pd.notna(rsi_series.iloc[-1]):
                rsi_slope = float(rsi_series.iloc[-1] - rsi_series.iloc[-2])

        if rsi_now is None:
            return 0.5

        distance_score = _clamp((oversold - float(rsi_now)) / max(oversold, 1.0))
        slope_score = _clamp(float(rsi_slope or 0.0) / 5.0)
        # Emphasize oversold depth, with optional slope confirmation.
        return _clamp(distance_score * 0.75 + slope_score * 0.25)

    @staticmethod
    def _signal_sma_component(signal: SignalSnapshot, data_handler: DataHandler) -> float:
        spread_norm = signal.extras.get("sma_spread_norm")

        if spread_norm is None:
            fast_period = int(signal.strategy_params.get("fast_period", 10))
            slow_period = int(signal.strategy_params.get("slow_period", 30))
            close = data_handler.data["close"]
            fast = BaseStrategy.sma(close, fast_period)
            slow = BaseStrategy.sma(close, slow_period)
            if len(fast) == 0 or len(slow) == 0 or pd.isna(fast.iloc[-1]) or pd.isna(slow.iloc[-1]):
                return 0.5
            spread = float(fast.iloc[-1] - slow.iloc[-1])
            atr_series = BaseStrategy.atr(
                high=data_handler.data["high"],
                low=data_handler.data["low"],
                close=data_handler.data["close"],
                period=14,
            )
            atr_now = atr_series.iloc[-1] if len(atr_series) > 0 else pd.NA
            if pd.notna(atr_now) and float(atr_now) > 0:
                spread_norm = spread / float(atr_now)
            else:
                price = float(close.iloc[-1])
                spread_norm = spread / price if price > 0 else 0.0

        # spread_norm around 0..1 is common; scale softly.
        return _clamp(float(spread_norm) / 1.5)

    def _risk_reward_component(self, setup: TradeSetup) -> float:
        rr = float(setup.risk_reward_ratio)
        if rr <= 0:
            return 0.0
        return _clamp(rr / self.rr_cap)

    def _trend_component(self, data_handler: DataHandler) -> float:
        close = data_handler.data["close"]

        if len(close) < self.trend_slow_period:
            return 0.5

        fast = close.rolling(self.trend_fast_period, min_periods=self.trend_fast_period).mean().iloc[-1]
        slow = close.rolling(self.trend_slow_period, min_periods=self.trend_slow_period).mean().iloc[-1]
        last = float(close.iloc[-1])

        if pd.isna(fast) or pd.isna(slow):
            return 0.5

        if last > fast > slow:
            return 1.0
        if last > fast:
            return 0.7
        return 0.3

    @staticmethod
    def _liquidity_component(data_handler: DataHandler) -> float:
        if "volume" not in data_handler.data.columns:
            return 0.5

        vol = data_handler.data["volume"].astype(float)
        if len(vol) < 20:
            return 0.5

        latest = float(vol.iloc[-1])
        avg20 = float(vol.tail(20).mean())

        if avg20 <= 0:
            return 0.5

        ratio = latest / avg20
        return _clamp(ratio / 2.0)

    def _freshness_component(self, signal: SignalSnapshot, data_handler: DataHandler) -> float:
        bars_since_trigger = signal.extras.get("bars_since_trigger")
        if bars_since_trigger is not None:
            return _clamp(1.0 - float(bars_since_trigger) / float(self.freshness_decay_bars))

        # Fallback when trigger age is unavailable.
        index = data_handler.data.index
        if len(index) == 0:
            return 0.0

        latest_ts = index[-1]
        if signal.timestamp == latest_ts:
            return 1.0

        try:
            latest_pos = len(index) - 1
            signal_pos = index.get_loc(signal.timestamp)
            if isinstance(signal_pos, slice):
                signal_pos = signal_pos.stop - 1
            if isinstance(signal_pos, (list, tuple)):
                signal_pos = signal_pos[-1]
            bars_ago = max(0, latest_pos - int(signal_pos))
            return _clamp(1.0 - bars_ago / float(self.freshness_decay_bars))
        except Exception:
            delta = latest_ts - signal.timestamp
            days = max(0.0, float(delta.total_seconds()) / 86400.0)
            return _clamp(1.0 - days / float(self.freshness_decay_bars))
