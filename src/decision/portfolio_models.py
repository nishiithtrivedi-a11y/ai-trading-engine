"""
Portfolio-aware decision support models for Phase 18.

These models are recommendation-only and never place orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import pandas as pd


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


class AllocationModel(str, Enum):
    EQUAL_WEIGHT = "equal_weight"
    VOLATILITY_WEIGHTED = "volatility_weighted"
    CONVICTION_WEIGHTED = "conviction_weighted"


class SizingMethod(str, Enum):
    FIXED_FRACTIONAL = "fixed_fractional"
    RISK_PER_TRADE = "risk_per_trade"
    ATR_BASED = "atr_based"


class DrawdownMode(str, Enum):
    NORMAL = "normal"
    REDUCED_RISK = "reduced_risk"
    NO_NEW_RISK = "no_new_risk"


class SelectionStatus(str, Enum):
    SELECTED = "selected"
    RESIZED = "resized"
    REJECTED = "rejected"


@dataclass
class DrawdownContext:
    daily_drawdown_pct: float = 0.0
    rolling_drawdown_pct: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.daily_drawdown_pct = float(self.daily_drawdown_pct)
        self.rolling_drawdown_pct = float(self.rolling_drawdown_pct)
        for value_name in ("daily_drawdown_pct", "rolling_drawdown_pct"):
            value = float(getattr(self, value_name))
            if value < 0:
                raise ValueError(f"{value_name} must be >= 0")


@dataclass
class PortfolioPlanItem:
    symbol: str
    canonical_symbol: str
    strategy_name: str
    timeframe: str
    confidence_score: float
    allocation_model: str
    allocation_percent: float
    allocation_amount: float
    sizing_method: str
    quantity: int
    notional_exposure: float
    estimated_entry: float
    estimated_stop: float
    estimated_target: float
    estimated_risk_amount: float
    estimated_risk_percent: float
    sector: str
    correlation_bucket: str
    correlation_note: str
    selection_status: SelectionStatus
    rejection_reason: str = ""
    resize_reason: str = ""
    drawdown_mode: DrawdownMode = DrawdownMode.NORMAL
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: pd.Timestamp = field(default_factory=_now_utc)
    schema_version: str = "v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at.isoformat(),
            "symbol": self.symbol,
            "canonical_symbol": self.canonical_symbol,
            "strategy": self.strategy_name,
            "strategy_name": self.strategy_name,
            "timeframe": self.timeframe,
            "confidence_score": self.confidence_score,
            "allocation_model": self.allocation_model,
            "allocation_percent": self.allocation_percent,
            "allocation_amount": self.allocation_amount,
            "sizing_method": self.sizing_method,
            "quantity": self.quantity,
            "notional_exposure": self.notional_exposure,
            "estimated_entry": self.estimated_entry,
            "estimated_stop": self.estimated_stop,
            "estimated_target": self.estimated_target,
            "estimated_risk_amount": self.estimated_risk_amount,
            "estimated_risk_percent": self.estimated_risk_percent,
            "sector": self.sector,
            "correlation_bucket": self.correlation_bucket,
            "correlation_note": self.correlation_note,
            "selection_status": self.selection_status.value,
            "rejection_reason": self.rejection_reason,
            "resize_reason": self.resize_reason,
            "drawdown_mode": self.drawdown_mode.value,
            "notes": "; ".join(self.notes),
            "metadata": dict(self.metadata),
        }


@dataclass
class PortfolioRiskSummary:
    schema_version: str = "v1"
    generated_at: pd.Timestamp = field(default_factory=_now_utc)
    drawdown_mode: DrawdownMode = DrawdownMode.NORMAL
    allocation_model: str = AllocationModel.CONVICTION_WEIGHTED.value
    sizing_method: str = SizingMethod.RISK_PER_TRADE.value
    total_candidates: int = 0
    selected_count: int = 0
    resized_count: int = 0
    rejected_count: int = 0
    deployed_capital: float = 0.0
    deployed_capital_pct: float = 0.0
    reserved_cash: float = 0.0
    estimated_total_risk_amount: float = 0.0
    estimated_total_risk_pct: float = 0.0
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at.isoformat(),
            "drawdown_mode": self.drawdown_mode.value,
            "allocation_model": self.allocation_model,
            "sizing_method": self.sizing_method,
            "total_candidates": self.total_candidates,
            "selected_count": self.selected_count,
            "resized_count": self.resized_count,
            "rejected_count": self.rejected_count,
            "deployed_capital": self.deployed_capital,
            "deployed_capital_pct": self.deployed_capital_pct,
            "reserved_cash": self.reserved_cash,
            "estimated_total_risk_amount": self.estimated_total_risk_amount,
            "estimated_total_risk_pct": self.estimated_total_risk_pct,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass
class PortfolioPlanResult:
    schema_version: str = "v1"
    generated_at: pd.Timestamp = field(default_factory=_now_utc)
    items: list[PortfolioPlanItem] = field(default_factory=list)
    summary: PortfolioRiskSummary = field(default_factory=PortfolioRiskSummary)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def selected_items(self) -> list[PortfolioPlanItem]:
        return [row for row in self.items if row.selection_status != SelectionStatus.REJECTED]

    @property
    def rejected_items(self) -> list[PortfolioPlanItem]:
        return [row for row in self.items if row.selection_status == SelectionStatus.REJECTED]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at.isoformat(),
            "summary": self.summary.to_dict(),
            "items": [item.to_dict() for item in self.items],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "metadata": dict(self.metadata),
        }

