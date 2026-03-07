"""
Core models for the Phase 5 decision/pick engine layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import pandas as pd


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


class DecisionHorizon(str, Enum):
    INTRADAY = "intraday"
    SWING = "swing"
    POSITIONAL = "positional"


class RejectionReason(str, Enum):
    BELOW_MIN_SCORE = "below_min_score"
    BELOW_MIN_RR = "below_min_rr"
    REGIME_BLOCKED = "regime_blocked"
    REGIME_PENALIZED_OUT = "regime_penalized_out"
    HORIZON_CAP_REACHED = "horizon_cap_reached"
    SECTOR_CAP_REACHED = "sector_cap_reached"
    DUPLICATE_SYMBOL = "duplicate_symbol"
    DUPLICATE_SETUP = "duplicate_setup"
    MISSING_CONTEXT = "missing_context"
    OTHER = "other"


@dataclass
class RegimeFilterResult:
    allowed: bool
    penalty: float = 0.0
    reasons: list[str] = field(default_factory=list)
    rejection_reasons: list[RejectionReason] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.penalty = float(self.penalty)
        if self.penalty < 0:
            raise ValueError("penalty must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "penalty": self.penalty,
            "reasons": list(self.reasons),
            "rejection_reasons": [r.value for r in self.rejection_reasons],
            "metadata": dict(self.metadata),
        }


@dataclass
class TradePlan:
    symbol: str
    timeframe: str
    strategy_name: str
    entry_price: float
    stop_loss: float
    target_price: float
    risk_reward: float
    horizon: DecisionHorizon
    setup_tags: list[str] = field(default_factory=list)
    max_hold_policy: str = "placeholder"
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = str(self.symbol).strip().upper()
        if not self.symbol:
            raise ValueError("symbol cannot be empty")
        if self.entry_price <= 0:
            raise ValueError("entry_price must be positive")
        if self.stop_loss <= 0:
            raise ValueError("stop_loss must be positive")
        if self.target_price <= 0:
            raise ValueError("target_price must be positive")
        if self.stop_loss >= self.entry_price:
            raise ValueError("For long-side plans, stop_loss must be below entry_price")
        if self.target_price <= self.entry_price:
            raise ValueError("For long-side plans, target_price must be above entry_price")
        if self.risk_reward <= 0:
            raise ValueError("risk_reward must be > 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "strategy_name": self.strategy_name,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "target_price": self.target_price,
            "risk_reward": self.risk_reward,
            "horizon": self.horizon.value,
            "setup_tags": list(self.setup_tags),
            "max_hold_policy": self.max_hold_policy,
            "notes": list(self.notes),
            "metadata": dict(self.metadata),
        }


@dataclass
class ConvictionBreakdown:
    scanner_score: float
    setup_quality: float
    risk_reward: float
    regime_compatibility: float
    relative_strength: float
    liquidity: float
    freshness: float
    final_score: float
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        fields = [
            "scanner_score",
            "setup_quality",
            "risk_reward",
            "regime_compatibility",
            "relative_strength",
            "liquidity",
            "freshness",
            "final_score",
        ]
        for name in fields:
            value = float(getattr(self, name))
            if not 0 <= value <= 100:
                raise ValueError(f"{name} must be in [0, 100]")
            setattr(self, name, value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanner_score": self.scanner_score,
            "setup_quality": self.setup_quality,
            "risk_reward": self.risk_reward,
            "regime_compatibility": self.regime_compatibility,
            "relative_strength": self.relative_strength,
            "liquidity": self.liquidity,
            "freshness": self.freshness,
            "final_score": self.final_score,
            "notes": list(self.notes),
            "metadata": dict(self.metadata),
        }


@dataclass
class RankedPick:
    trade_plan: TradePlan
    conviction_score: float
    conviction_breakdown: ConvictionBreakdown
    scanner_score: float
    regime_compatibility: Optional[float] = None
    relative_strength_score: Optional[float] = None
    priority_rank: Optional[int] = None
    horizon_rank: Optional[int] = None
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.conviction_score = float(self.conviction_score)
        self.scanner_score = float(self.scanner_score)
        if not 0 <= self.conviction_score <= 100:
            raise ValueError("conviction_score must be in [0, 100]")
        if not 0 <= self.scanner_score <= 100:
            raise ValueError("scanner_score must be in [0, 100]")

    @property
    def horizon(self) -> DecisionHorizon:
        return self.trade_plan.horizon

    @property
    def symbol(self) -> str:
        return self.trade_plan.symbol

    @property
    def sector(self) -> Optional[str]:
        return self.trade_plan.metadata.get("sector")

    def to_dict(self) -> dict[str, Any]:
        row = {
            "priority_rank": self.priority_rank,
            "horizon_rank": self.horizon_rank,
            "conviction_score": self.conviction_score,
            "scanner_score": self.scanner_score,
            "regime_compatibility": self.regime_compatibility,
            "relative_strength_score": self.relative_strength_score,
            "reasons": "; ".join(self.reasons),
            "metadata": dict(self.metadata),
            "conviction_breakdown": self.conviction_breakdown.to_dict(),
        }
        row.update(self.trade_plan.to_dict())
        return row


@dataclass
class RejectedOpportunity:
    symbol: str
    timeframe: str
    strategy_name: str
    horizon: DecisionHorizon
    scanner_score: Optional[float]
    rejection_reasons: list[RejectionReason] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = str(self.symbol).strip().upper()
        if not self.symbol:
            raise ValueError("symbol cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "strategy_name": self.strategy_name,
            "horizon": self.horizon.value,
            "scanner_score": self.scanner_score,
            "rejection_reasons": "; ".join(r.value for r in self.rejection_reasons),
            "notes": "; ".join(self.notes),
            "metadata": dict(self.metadata),
        }


@dataclass
class PickRunResult:
    generated_at: pd.Timestamp = field(default_factory=_now_utc)
    selected_picks: list[RankedPick] = field(default_factory=list)
    top_intraday: list[RankedPick] = field(default_factory=list)
    top_swing: list[RankedPick] = field(default_factory=list)
    top_positional: list[RankedPick] = field(default_factory=list)
    rejected_opportunities: list[RejectedOpportunity] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    exports: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "summary": {
                "selected_total": len(self.selected_picks),
                "intraday_total": len(self.top_intraday),
                "swing_total": len(self.top_swing),
                "positional_total": len(self.top_positional),
                "rejected_total": len(self.rejected_opportunities),
                "warnings_total": len(self.warnings),
                "errors_total": len(self.errors),
            },
            "top_intraday": [p.to_dict() for p in self.top_intraday],
            "top_swing": [p.to_dict() for p in self.top_swing],
            "top_positional": [p.to_dict() for p in self.top_positional],
            "rejected_opportunities": [r.to_dict() for r in self.rejected_opportunities],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "exports": dict(self.exports),
            "metadata": dict(self.metadata),
        }
