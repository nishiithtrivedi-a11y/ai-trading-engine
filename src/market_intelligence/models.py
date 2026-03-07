"""
Core models for the Phase 6 market intelligence layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import pandas as pd


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


class BreadthState(str, Enum):
    STRONG = "strong"
    NEUTRAL = "neutral"
    WEAK = "weak"
    UNKNOWN = "unknown"


class SectorRotationState(str, Enum):
    LEADING = "leading"
    WEAKENING = "weakening"
    LAGGING = "lagging"
    UNKNOWN = "unknown"


class VolumeSignalType(str, Enum):
    SPIKE = "spike"
    ACCUMULATION = "accumulation"
    DISTRIBUTION = "distribution"
    VW_MOMENTUM = "volume_weighted_momentum"


class VolatilityRegimeType(str, Enum):
    LOW = "low_volatility"
    EXPANDING = "expanding_volatility"
    HIGH = "high_volatility"
    CONTRACTION = "volatility_contraction"
    UNKNOWN = "unknown"


class TrendState(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGEBOUND = "rangebound"
    UNKNOWN = "unknown"


class RiskEnvironment(str, Enum):
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    NEUTRAL = "neutral"


@dataclass
class BreadthMetrics:
    advancing_count: int
    declining_count: int
    unchanged_count: int = 0
    ad_ratio: float = 0.0
    ad_line: float = 0.0
    pct_above_ma: float = 0.0
    pct_new_highs: float = 0.0
    pct_new_lows: float = 0.0
    universe_size: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "advancing_count": self.advancing_count,
            "declining_count": self.declining_count,
            "unchanged_count": self.unchanged_count,
            "ad_ratio": self.ad_ratio,
            "ad_line": self.ad_line,
            "pct_above_ma": self.pct_above_ma,
            "pct_new_highs": self.pct_new_highs,
            "pct_new_lows": self.pct_new_lows,
            "universe_size": self.universe_size,
            "metadata": dict(self.metadata),
        }


@dataclass
class BreadthSnapshot:
    timestamp: pd.Timestamp
    timeframe: str
    metrics: BreadthMetrics
    breadth_state: BreadthState = BreadthState.UNKNOWN
    benchmark_symbol: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        row = {
            "timestamp": self.timestamp.isoformat(),
            "timeframe": self.timeframe,
            "breadth_state": self.breadth_state.value,
            "benchmark_symbol": self.benchmark_symbol,
            "metadata": dict(self.metadata),
        }
        row.update(self.metrics.to_dict())
        return row


@dataclass
class SectorStrengthSnapshot:
    sector: str
    score: float
    rank: Optional[int] = None
    state: SectorRotationState = SectorRotationState.UNKNOWN
    lookback_returns: dict[str, float] = field(default_factory=dict)
    benchmark_relative_return: Optional[float] = None
    top_symbols: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sector": self.sector,
            "score": float(self.score),
            "rank": self.rank,
            "state": self.state.value,
            "benchmark_relative_return": self.benchmark_relative_return,
            "top_symbols": list(self.top_symbols),
            "lookback_returns": dict(self.lookback_returns),
            "metadata": dict(self.metadata),
        }


@dataclass
class VolumeSignal:
    symbol: str
    signal_type: VolumeSignalType
    strength: float
    timestamp: pd.Timestamp
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "signal_type": self.signal_type.value,
            "strength": float(self.strength),
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


@dataclass
class VolumeAnalysisSnapshot:
    symbol: str
    timeframe: str
    timestamp: pd.Timestamp
    signals: list[VolumeSignal] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp.isoformat(),
            "signals": [signal.to_dict() for signal in self.signals],
            "metrics": dict(self.metrics),
            "metadata": dict(self.metadata),
        }


@dataclass
class VolatilityRegimeSnapshot:
    symbol: str
    timeframe: str
    timestamp: pd.Timestamp
    regime: VolatilityRegimeType
    realized_volatility: float
    atr_value: float
    atr_ratio: float
    state_score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp.isoformat(),
            "regime": self.regime.value,
            "realized_volatility": float(self.realized_volatility),
            "atr_value": float(self.atr_value),
            "atr_ratio": float(self.atr_ratio),
            "state_score": float(self.state_score),
            "metadata": dict(self.metadata),
        }


@dataclass
class InstitutionalFlowSnapshot:
    timestamp: pd.Timestamp = field(default_factory=_now_utc)
    data_available: bool = False
    fii_net: Optional[float] = None
    dii_net: Optional[float] = None
    block_trade_notional: Optional[float] = None
    summary: str = "institutional flow data unavailable"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "data_available": self.data_available,
            "fii_net": self.fii_net,
            "dii_net": self.dii_net,
            "block_trade_notional": self.block_trade_notional,
            "summary": self.summary,
            "metadata": dict(self.metadata),
        }


@dataclass
class MarketStateAssessment:
    timestamp: pd.Timestamp = field(default_factory=_now_utc)
    trend_state: TrendState = TrendState.UNKNOWN
    breadth_state: BreadthState = BreadthState.UNKNOWN
    sector_leaders: list[str] = field(default_factory=list)
    volatility_regime: VolatilityRegimeType = VolatilityRegimeType.UNKNOWN
    risk_environment: RiskEnvironment = RiskEnvironment.NEUTRAL
    confidence_score: float = 0.0
    summary_reasons: list[str] = field(default_factory=list)
    components: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.confidence_score = max(0.0, min(100.0, float(self.confidence_score)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "trend_state": self.trend_state.value,
            "breadth_state": self.breadth_state.value,
            "sector_leaders": list(self.sector_leaders),
            "volatility_regime": self.volatility_regime.value,
            "risk_environment": self.risk_environment.value,
            "confidence_score": self.confidence_score,
            "summary_reasons": list(self.summary_reasons),
            "components": dict(self.components),
            "metadata": dict(self.metadata),
        }


@dataclass
class MarketIntelligenceResult:
    generated_at: pd.Timestamp = field(default_factory=_now_utc)
    breadth_snapshot: Optional[BreadthSnapshot] = None
    sector_rotation: list[SectorStrengthSnapshot] = field(default_factory=list)
    volume_analysis: list[VolumeAnalysisSnapshot] = field(default_factory=list)
    volatility_snapshot: Optional[VolatilityRegimeSnapshot] = None
    institutional_flow: Optional[InstitutionalFlowSnapshot] = None
    market_state: Optional[MarketStateAssessment] = None
    exports: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "breadth_snapshot": (
                self.breadth_snapshot.to_dict() if self.breadth_snapshot else None
            ),
            "sector_rotation": [row.to_dict() for row in self.sector_rotation],
            "volume_analysis": [row.to_dict() for row in self.volume_analysis],
            "volatility_snapshot": (
                self.volatility_snapshot.to_dict() if self.volatility_snapshot else None
            ),
            "institutional_flow": (
                self.institutional_flow.to_dict() if self.institutional_flow else None
            ),
            "market_state": self.market_state.to_dict() if self.market_state else None,
            "exports": dict(self.exports),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }
