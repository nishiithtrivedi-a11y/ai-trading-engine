"""
Core data models for the scanner pipeline.

These models are intentionally simple and explicit so other scanner
modules can compose them without hidden behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import pandas as pd


class OpportunityClass(str, Enum):
    INTRADAY = "intraday"
    SWING = "swing"
    POSITIONAL = "positional"


class OpportunitySide(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class SignalSnapshot:
    symbol: str
    timeframe: str
    strategy_name: str
    signal: str
    timestamp: pd.Timestamp
    close_price: float
    strategy_params: dict[str, Any] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)

    ACTIONABLE_SIGNALS = {"buy"}

    def __post_init__(self) -> None:
        self.signal = str(self.signal).strip().lower()
        if self.close_price <= 0:
            raise ValueError("close_price must be positive")

    @property
    def is_actionable(self) -> bool:
        return self.signal in self.ACTIONABLE_SIGNALS

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "strategy_name": self.strategy_name,
            "signal": self.signal,
            "timestamp": str(self.timestamp),
            "close_price": self.close_price,
            "strategy_params": self.strategy_params,
            "extras": self.extras,
            "is_actionable": self.is_actionable,
        }


@dataclass
class TradeSetup:
    entry_price: float
    stop_loss: float
    target_price: float
    side: OpportunitySide = OpportunitySide.LONG
    risk_model: str = "atr_r_multiple"
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.entry_price <= 0:
            raise ValueError("entry_price must be positive")
        if self.stop_loss <= 0:
            raise ValueError("stop_loss must be positive")
        if self.target_price <= 0:
            raise ValueError("target_price must be positive")

        if self.side == OpportunitySide.LONG:
            if self.stop_loss >= self.entry_price:
                raise ValueError("For long setups, stop_loss must be below entry_price")
            if self.target_price <= self.entry_price:
                raise ValueError("For long setups, target_price must be above entry_price")
        elif self.side == OpportunitySide.SHORT:
            if self.stop_loss <= self.entry_price:
                raise ValueError("For short setups, stop_loss must be above entry_price")
            if self.target_price >= self.entry_price:
                raise ValueError("For short setups, target_price must be below entry_price")

    @property
    def risk_per_unit(self) -> float:
        if self.side == OpportunitySide.LONG:
            return self.entry_price - self.stop_loss
        return self.stop_loss - self.entry_price

    @property
    def reward_per_unit(self) -> float:
        if self.side == OpportunitySide.LONG:
            return self.target_price - self.entry_price
        return self.entry_price - self.target_price

    @property
    def risk_reward_ratio(self) -> float:
        risk = self.risk_per_unit
        if risk <= 0:
            return 0.0
        return self.reward_per_unit / risk

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "target_price": self.target_price,
            "side": self.side.value,
            "risk_model": self.risk_model,
            "risk_per_unit": self.risk_per_unit,
            "reward_per_unit": self.reward_per_unit,
            "risk_reward_ratio": self.risk_reward_ratio,
            "extras": self.extras,
        }


@dataclass
class Opportunity:
    symbol: str
    timeframe: str
    strategy_name: str
    signal: str
    timestamp: pd.Timestamp
    classification: OpportunityClass
    entry_price: float
    stop_loss: float
    target_price: float
    side: OpportunitySide = OpportunitySide.LONG
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    # Flattened score components for export friendliness
    score_signal: Optional[float] = None
    score_rr: Optional[float] = None
    score_trend: Optional[float] = None
    score_liquidity: Optional[float] = None
    score_freshness: Optional[float] = None
    rank: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "strategy_name": self.strategy_name,
            "signal": self.signal,
            "timestamp": str(self.timestamp),
            "classification": self.classification.value,
            "side": self.side.value,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "target_price": self.target_price,
            "score": self.score,
            "score_signal": self.score_signal,
            "score_rr": self.score_rr,
            "score_trend": self.score_trend,
            "score_liquidity": self.score_liquidity,
            "score_freshness": self.score_freshness,
            "reasons": "; ".join(self.reasons),
            "metadata": self.metadata,
        }

    @classmethod
    def from_parts(
        cls,
        snapshot: SignalSnapshot,
        setup: TradeSetup,
        classification: OpportunityClass,
        score: float,
        reasons: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        score_components: Optional[dict[str, float]] = None,
    ) -> Opportunity:
        score_components = score_components or {}
        return cls(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            strategy_name=snapshot.strategy_name,
            signal=snapshot.signal,
            timestamp=snapshot.timestamp,
            classification=classification,
            entry_price=setup.entry_price,
            stop_loss=setup.stop_loss,
            target_price=setup.target_price,
            side=setup.side,
            score=float(score),
            reasons=reasons or [],
            metadata=metadata or {},
            score_signal=score_components.get("signal"),
            score_rr=score_components.get("risk_reward"),
            score_trend=score_components.get("trend"),
            score_liquidity=score_components.get("liquidity"),
            score_freshness=score_components.get("freshness"),
        )


@dataclass
class ScanResult:
    opportunities: list[Opportunity] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    universe_name: str = ""
    provider_name: str = ""
    num_symbols_scanned: int = 0
    num_jobs: int = 0
    num_errors: int = 0
    errors: list[str] = field(default_factory=list)

    def get_top(self, n: int = 20) -> list[Opportunity]:
        ranked = sorted(
            self.opportunities,
            key=lambda o: float(o.score),
            reverse=True,
        )
        top = ranked[:n]
        for idx, opp in enumerate(top, start=1):
            opp.rank = idx
        return top

    def to_dataframe(self, top_n: Optional[int] = None) -> pd.DataFrame:
        rows = self.opportunities if top_n is None else self.get_top(top_n)
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([o.to_dict() for o in rows])

    def to_dict(self, top_n: Optional[int] = None) -> dict[str, Any]:
        rows = self.opportunities if top_n is None else self.get_top(top_n)
        return {
            "generated_at": self.generated_at.isoformat(),
            "universe_name": self.universe_name,
            "provider_name": self.provider_name,
            "num_symbols_scanned": self.num_symbols_scanned,
            "num_jobs": self.num_jobs,
            "num_errors": self.num_errors,
            "total_opportunities": len(self.opportunities),
            "opportunities": [o.to_dict() for o in rows],
            "errors": self.errors,
        }
