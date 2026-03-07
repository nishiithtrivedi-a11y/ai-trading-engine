"""
Core models for the Phase 7 strategy research lab.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from src.strategies.base_strategy import BaseStrategy


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class StrategyCandidate:
    strategy_class: type[BaseStrategy]
    params: dict[str, Any]
    template_name: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def strategy_name(self) -> str:
        return self.strategy_class.__name__

    def key(self) -> str:
        parts = [f"{k}={self.params[k]}" for k in sorted(self.params)]
        return f"{self.strategy_name}|" + "|".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "params": dict(self.params),
            "template_name": self.template_name,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
            "key": self.key(),
        }


@dataclass
class ParameterSurfacePoint:
    strategy_name: str
    params: dict[str, Any]
    sharpe_ratio: float
    max_drawdown_pct: float
    profit_factor: float
    total_return_pct: float
    num_trades: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        row = {
            "strategy_name": self.strategy_name,
            "sharpe_ratio": float(self.sharpe_ratio),
            "max_drawdown_pct": float(self.max_drawdown_pct),
            "profit_factor": float(self.profit_factor),
            "total_return_pct": float(self.total_return_pct),
            "num_trades": int(self.num_trades),
            "metadata": dict(self.metadata),
        }
        for k, v in self.params.items():
            row[f"param_{k}"] = v
        row["params"] = dict(self.params)
        return row


@dataclass
class ParameterSurfaceReport:
    strategy_name: str
    points: list[ParameterSurfacePoint] = field(default_factory=list)
    stable_region_keys: list[str] = field(default_factory=list)
    unstable_region_keys: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "num_points": len(self.points),
            "stable_region_keys": list(self.stable_region_keys),
            "unstable_region_keys": list(self.unstable_region_keys),
            "points": [p.to_dict() for p in self.points],
            "metadata": dict(self.metadata),
        }


@dataclass
class RobustnessReport:
    strategy_name: str
    params: dict[str, Any]
    walk_forward_score: float
    monte_carlo_score: float
    noise_resilience_score: float
    parameter_stability_score: float
    overall_robustness_score: float
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in [
            "walk_forward_score",
            "monte_carlo_score",
            "noise_resilience_score",
            "parameter_stability_score",
            "overall_robustness_score",
        ]:
            value = float(getattr(self, field_name))
            value = max(0.0, min(100.0, value))
            setattr(self, field_name, value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "params": dict(self.params),
            "walk_forward_score": self.walk_forward_score,
            "monte_carlo_score": self.monte_carlo_score,
            "noise_resilience_score": self.noise_resilience_score,
            "parameter_stability_score": self.parameter_stability_score,
            "overall_robustness_score": self.overall_robustness_score,
            "notes": list(self.notes),
            "metadata": dict(self.metadata),
        }


@dataclass
class StrategyCluster:
    cluster_id: int
    strategy_keys: list[str] = field(default_factory=list)
    centroid_metrics: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "strategy_keys": list(self.strategy_keys),
            "cluster_size": len(self.strategy_keys),
            "centroid_metrics": dict(self.centroid_metrics),
            "metadata": dict(self.metadata),
        }


@dataclass
class StrategyScore:
    strategy_name: str
    params: dict[str, Any]
    strategy_key: str
    sharpe_component: float
    drawdown_component: float
    robustness_component: float
    consistency_component: float
    trade_frequency_component: float
    risk_adjusted_component: float
    total_score: float
    rank: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in [
            "sharpe_component",
            "drawdown_component",
            "robustness_component",
            "consistency_component",
            "trade_frequency_component",
            "risk_adjusted_component",
            "total_score",
        ]:
            value = float(getattr(self, field_name))
            value = max(0.0, min(100.0, value))
            setattr(self, field_name, value)

    def to_dict(self) -> dict[str, Any]:
        row = {
            "rank": self.rank,
            "strategy_name": self.strategy_name,
            "strategy_key": self.strategy_key,
            "sharpe_component": self.sharpe_component,
            "drawdown_component": self.drawdown_component,
            "robustness_component": self.robustness_component,
            "consistency_component": self.consistency_component,
            "trade_frequency_component": self.trade_frequency_component,
            "risk_adjusted_component": self.risk_adjusted_component,
            "total_score": self.total_score,
            "metadata": dict(self.metadata),
            "params": dict(self.params),
        }
        for k, v in self.params.items():
            row[f"param_{k}"] = v
        return row


@dataclass
class StrategyDiscoveryResult:
    generated_at: datetime = field(default_factory=_now_utc)
    total_candidates: int = 0
    total_evaluated: int = 0
    strategy_scores: list[StrategyScore] = field(default_factory=list)
    strategy_clusters: list[StrategyCluster] = field(default_factory=list)
    robustness_reports: list[RobustnessReport] = field(default_factory=list)
    parameter_surfaces: list[ParameterSurfaceReport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    exports: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "summary": {
                "total_candidates": self.total_candidates,
                "total_evaluated": self.total_evaluated,
                "num_scores": len(self.strategy_scores),
                "num_clusters": len(self.strategy_clusters),
                "num_robustness_reports": len(self.robustness_reports),
                "num_parameter_surfaces": len(self.parameter_surfaces),
            },
            "strategy_scores": [s.to_dict() for s in self.strategy_scores],
            "strategy_clusters": [c.to_dict() for c in self.strategy_clusters],
            "robustness_reports": [r.to_dict() for r in self.robustness_reports],
            "parameter_surfaces": [p.to_dict() for p in self.parameter_surfaces],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "exports": dict(self.exports),
        }
