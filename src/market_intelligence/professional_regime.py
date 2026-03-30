"""
Professional intraday regime classification layered on top of legacy regime outputs.

This module is additive and backward-compatible:
- it does not modify MarketRegimeEngine behavior
- it maps legacy composite regimes to a richer professional regime set
- it exposes deterministic, threshold-based logic for research workflows
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.market_intelligence.models import CompositeRegime, MarketRegimeSnapshot
from src.strategies.base_strategy import BaseStrategy


class ProfessionalRegime(str, Enum):
    BULL_TREND = "BULL_TREND"
    BULL_VOLATILE = "BULL_VOLATILE"
    BEAR_TREND = "BEAR_TREND"
    BEAR_VOLATILE = "BEAR_VOLATILE"
    SIDEWAYS_RANGE = "SIDEWAYS_RANGE"
    CHOPPY_NOISE = "CHOPPY_NOISE"
    COMPRESSION = "COMPRESSION"
    EXPANSION = "EXPANSION"
    REVERSAL = "REVERSAL"
    UNKNOWN = "UNKNOWN"


PROFESSIONAL_REGIME_ORDER: tuple[ProfessionalRegime, ...] = (
    ProfessionalRegime.BULL_TREND,
    ProfessionalRegime.BULL_VOLATILE,
    ProfessionalRegime.BEAR_TREND,
    ProfessionalRegime.BEAR_VOLATILE,
    ProfessionalRegime.SIDEWAYS_RANGE,
    ProfessionalRegime.CHOPPY_NOISE,
    ProfessionalRegime.COMPRESSION,
    ProfessionalRegime.EXPANSION,
    ProfessionalRegime.REVERSAL,
)


_LEGACY_TO_PROFESSIONAL: dict[str, ProfessionalRegime] = {
    CompositeRegime.BULLISH_TRENDING.value: ProfessionalRegime.BULL_TREND,
    CompositeRegime.BULLISH_SIDEWAYS.value: ProfessionalRegime.SIDEWAYS_RANGE,
    CompositeRegime.BEARISH_TRENDING.value: ProfessionalRegime.BEAR_TREND,
    CompositeRegime.BEARISH_VOLATILE.value: ProfessionalRegime.BEAR_VOLATILE,
    CompositeRegime.RANGEBOUND.value: ProfessionalRegime.SIDEWAYS_RANGE,
    CompositeRegime.RISK_OFF.value: ProfessionalRegime.EXPANSION,
    CompositeRegime.UNKNOWN.value: ProfessionalRegime.UNKNOWN,
}


@dataclass
class ProfessionalRegimeConfig:
    min_bars: int = 120
    fast_ema_period: int = 20
    slow_ema_period: int = 50
    atr_period: int = 14
    atr_baseline_period: int = 50
    realized_vol_window: int = 40
    baseline_vol_window: int = 120
    range_lookback: int = 40
    efficiency_lookback: int = 30
    chop_lookback: int = 30
    reversal_lookback: int = 24
    trend_threshold: float = 0.0018
    expansion_atr_ratio_min: float = 1.18
    compression_atr_ratio_max: float = 0.86
    expansion_vol_multiple: float = 1.15
    compression_vol_multiple: float = 0.75
    sideways_range_width_max: float = 0.025
    compression_range_width_max: float = 0.018
    sideways_atr_ratio_max: float = 1.05
    choppy_efficiency_max: float = 0.23
    chop_min_crossovers: int = 6


@dataclass
class ProfessionalRegimeSnapshot:
    symbol: str
    timestamp: pd.Timestamp
    regime: ProfessionalRegime
    reason: str
    trend_score: Optional[float] = None
    prior_trend_score: Optional[float] = None
    realized_volatility: Optional[float] = None
    baseline_volatility: Optional[float] = None
    atr_ratio: Optional[float] = None
    range_width: Optional[float] = None
    path_efficiency: Optional[float] = None
    crossover_count: Optional[int] = None
    legacy_composite_regime: Optional[str] = None
    bars_used: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "regime": self.regime.value,
            "reason": self.reason,
            "trend_score": self.trend_score,
            "prior_trend_score": self.prior_trend_score,
            "realized_volatility": self.realized_volatility,
            "baseline_volatility": self.baseline_volatility,
            "atr_ratio": self.atr_ratio,
            "range_width": self.range_width,
            "path_efficiency": self.path_efficiency,
            "crossover_count": self.crossover_count,
            "legacy_composite_regime": self.legacy_composite_regime,
            "bars_used": self.bars_used,
            "metadata": dict(self.metadata),
        }


def legacy_to_professional_regime(
    legacy_composite_regime: str | CompositeRegime,
) -> ProfessionalRegime:
    raw = (
        legacy_composite_regime.value
        if isinstance(legacy_composite_regime, CompositeRegime)
        else str(legacy_composite_regime).strip().lower()
    )
    return _LEGACY_TO_PROFESSIONAL.get(raw, ProfessionalRegime.UNKNOWN)


def _estimate_bars_per_year(index: pd.Index) -> float:
    if not isinstance(index, pd.DatetimeIndex) or len(index) < 3:
        return 252.0
    diffs = pd.Series(index).diff().dropna()
    if diffs.empty:
        return 252.0
    median_seconds = float(diffs.dt.total_seconds().median())
    if median_seconds <= 0:
        return 252.0
    seconds_per_year = 365.0 * 24.0 * 60.0 * 60.0
    return max(seconds_per_year / median_seconds, 252.0)


@dataclass
class ProfessionalRegimeClassifier:
    config: ProfessionalRegimeConfig = field(default_factory=ProfessionalRegimeConfig)

    def detect(
        self,
        df: pd.DataFrame,
        *,
        symbol: str = "UNKNOWN",
        legacy_snapshot: Optional[MarketRegimeSnapshot] = None,
    ) -> ProfessionalRegimeSnapshot:
        cfg = self.config
        now_ts = pd.Timestamp(df.index[-1]) if len(df.index) else pd.Timestamp.now(tz="UTC")
        legacy_regime = legacy_snapshot.composite_regime.value if legacy_snapshot else None

        required = {"high", "low", "close"}
        missing = required - set(df.columns)
        if missing:
            return ProfessionalRegimeSnapshot(
                symbol=symbol,
                timestamp=now_ts,
                regime=ProfessionalRegime.UNKNOWN,
                reason=f"missing_columns={sorted(missing)}",
                legacy_composite_regime=legacy_regime,
                bars_used=len(df),
            )
        if len(df) < cfg.min_bars:
            fallback = (
                legacy_to_professional_regime(legacy_regime)
                if legacy_regime
                else ProfessionalRegime.UNKNOWN
            )
            return ProfessionalRegimeSnapshot(
                symbol=symbol,
                timestamp=now_ts,
                regime=fallback,
                reason=f"insufficient_bars={len(df)}<{cfg.min_bars}",
                legacy_composite_regime=legacy_regime,
                bars_used=len(df),
            )

        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)

        ema_fast = close.ewm(span=cfg.fast_ema_period, adjust=False, min_periods=cfg.fast_ema_period).mean()
        ema_slow = close.ewm(span=cfg.slow_ema_period, adjust=False, min_periods=cfg.slow_ema_period).mean()
        if pd.isna(ema_fast.iloc[-1]) or pd.isna(ema_slow.iloc[-1]) or float(ema_slow.iloc[-1]) == 0.0:
            fallback = (
                legacy_to_professional_regime(legacy_regime)
                if legacy_regime
                else ProfessionalRegime.UNKNOWN
            )
            return ProfessionalRegimeSnapshot(
                symbol=symbol,
                timestamp=now_ts,
                regime=fallback,
                reason="invalid_ema_inputs",
                legacy_composite_regime=legacy_regime,
                bars_used=len(df),
            )

        trend_score = float((ema_fast.iloc[-1] - ema_slow.iloc[-1]) / ema_slow.iloc[-1])
        prior_idx = max(0, len(close) - cfg.reversal_lookback - 1)
        prior_slow = float(ema_slow.iloc[prior_idx]) if not pd.isna(ema_slow.iloc[prior_idx]) else 0.0
        prior_trend_score = (
            float((ema_fast.iloc[prior_idx] - ema_slow.iloc[prior_idx]) / prior_slow)
            if prior_slow != 0.0
            else 0.0
        )

        returns = close.pct_change().dropna()
        bars_per_year = _estimate_bars_per_year(df.index)
        realized_slice = returns.tail(cfg.realized_vol_window)
        baseline_slice = returns.tail(max(cfg.baseline_vol_window, cfg.realized_vol_window))
        realized_vol = float(realized_slice.std() * np.sqrt(bars_per_year)) if len(realized_slice) > 1 else 0.0
        baseline_vol = float(baseline_slice.std() * np.sqrt(bars_per_year)) if len(baseline_slice) > 1 else max(realized_vol, 1e-9)
        if baseline_vol <= 0:
            baseline_vol = max(realized_vol, 1e-9)

        atr_series = BaseStrategy.atr(high=high, low=low, close=close, period=cfg.atr_period)
        atr_latest = float(atr_series.iloc[-1]) if pd.notna(atr_series.iloc[-1]) else 0.0
        atr_baseline = float(atr_series.tail(cfg.atr_baseline_period).mean())
        atr_ratio = (atr_latest / atr_baseline) if atr_baseline > 0 else 0.0

        range_high = float(high.tail(cfg.range_lookback).max())
        range_low = float(low.tail(cfg.range_lookback).min())
        last_close = float(close.iloc[-1])
        range_width = (range_high - range_low) / max(last_close, 1e-9)

        path = close.tail(cfg.efficiency_lookback)
        path_move = float(path.diff().abs().sum()) if len(path) > 1 else 0.0
        path_efficiency = (
            float(abs(path.iloc[-1] - path.iloc[0]) / max(path_move, 1e-9))
            if len(path) > 1
            else 0.0
        )

        diff_sign = np.sign((close - ema_fast).tail(cfg.chop_lookback).fillna(0.0))
        sign_series = pd.Series(diff_sign, index=(close - ema_fast).tail(cfg.chop_lookback).index)
        crossover_count = int(((sign_series * sign_series.shift(1)) < 0).sum())

        bull_trend = (
            trend_score >= cfg.trend_threshold
            and last_close > float(ema_fast.iloc[-1]) > float(ema_slow.iloc[-1])
        )
        bear_trend = (
            trend_score <= -cfg.trend_threshold
            and last_close < float(ema_fast.iloc[-1]) < float(ema_slow.iloc[-1])
        )
        expansion = (
            atr_ratio >= cfg.expansion_atr_ratio_min
            and realized_vol >= baseline_vol * cfg.expansion_vol_multiple
        )
        compression = (
            atr_ratio <= cfg.compression_atr_ratio_max
            and realized_vol <= baseline_vol * cfg.compression_vol_multiple
            and range_width <= cfg.compression_range_width_max
        )
        sideways = (
            abs(trend_score) <= cfg.trend_threshold
            and range_width <= cfg.sideways_range_width_max
            and atr_ratio <= cfg.sideways_atr_ratio_max
        )
        choppy = (
            path_efficiency <= cfg.choppy_efficiency_max
            and crossover_count >= cfg.chop_min_crossovers
            and not bull_trend
            and not bear_trend
        )
        reversal = (
            np.sign(trend_score) != np.sign(prior_trend_score)
            and abs(trend_score) >= cfg.trend_threshold
            and abs(prior_trend_score) >= cfg.trend_threshold
            and expansion
        )

        if reversal:
            regime = ProfessionalRegime.REVERSAL
            reason = "trend_sign_flip_with_expansion"
        elif compression:
            regime = ProfessionalRegime.COMPRESSION
            reason = "low_vol_low_atr_tight_range"
        elif bull_trend and expansion:
            regime = ProfessionalRegime.BULL_VOLATILE
            reason = "bull_trend_with_expanding_vol"
        elif bear_trend and expansion:
            regime = ProfessionalRegime.BEAR_VOLATILE
            reason = "bear_trend_with_expanding_vol"
        elif bull_trend:
            regime = ProfessionalRegime.BULL_TREND
            reason = "bull_trend_structure"
        elif bear_trend:
            regime = ProfessionalRegime.BEAR_TREND
            reason = "bear_trend_structure"
        elif sideways:
            regime = ProfessionalRegime.SIDEWAYS_RANGE
            reason = "flat_trend_tight_range"
        elif choppy:
            regime = ProfessionalRegime.CHOPPY_NOISE
            reason = "low_efficiency_high_cross_noise"
        elif expansion:
            regime = ProfessionalRegime.EXPANSION
            reason = "volatility_expansion_without_clear_trend"
        elif legacy_regime:
            regime = legacy_to_professional_regime(legacy_regime)
            reason = "legacy_compatibility_fallback"
        else:
            regime = ProfessionalRegime.UNKNOWN
            reason = "no_rule_triggered"

        return ProfessionalRegimeSnapshot(
            symbol=symbol,
            timestamp=now_ts,
            regime=regime,
            reason=reason,
            trend_score=trend_score,
            prior_trend_score=prior_trend_score,
            realized_volatility=realized_vol,
            baseline_volatility=baseline_vol,
            atr_ratio=atr_ratio,
            range_width=range_width,
            path_efficiency=path_efficiency,
            crossover_count=crossover_count,
            legacy_composite_regime=legacy_regime,
            bars_used=len(df),
            metadata={
                "bull_trend": bull_trend,
                "bear_trend": bear_trend,
                "expansion": expansion,
                "compression": compression,
                "sideways": sideways,
                "choppy": choppy,
                "reversal": reversal,
            },
        )
