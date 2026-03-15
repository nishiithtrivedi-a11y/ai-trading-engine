"""
Core models for the Phase 9 live-safe market data and signal pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


@dataclass
class LiveMarketSnapshot:
    symbol: str
    timeframe: str
    timestamp: pd.Timestamp
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    bars_loaded: int
    provider_name: str
    source: str = "latest_available_bar"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp.isoformat(),
            "open": self.open_price,
            "high": self.high_price,
            "low": self.low_price,
            "close": self.close_price,
            "volume": self.volume,
            "bars_loaded": self.bars_loaded,
            "provider_name": self.provider_name,
            "source": self.source,
            "metadata": dict(self.metadata),
        }


@dataclass
class SignalDecision:
    symbol: str
    timeframe: str
    strategy_name: str
    signal: str
    timestamp: pd.Timestamp
    close_price: float
    decision_type: str
    reason: str
    regime_label: str = "unknown"
    risk_allowed: Optional[bool] = None
    paper_handoff_eligible: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "strategy_name": self.strategy_name,
            "signal": self.signal,
            "timestamp": self.timestamp.isoformat(),
            "close_price": self.close_price,
            "decision_type": self.decision_type,
            "reason": self.reason,
            "regime_label": self.regime_label,
            "risk_allowed": self.risk_allowed,
            "paper_handoff_eligible": self.paper_handoff_eligible,
            "metadata": dict(self.metadata),
        }


@dataclass
class WatchlistState:
    session_label: str
    provider_name: str
    universe_name: str
    timeframe: str
    requested_symbols: list[str] = field(default_factory=list)
    loaded_symbols: list[str] = field(default_factory=list)
    ranked_symbols: list[str] = field(default_factory=list)
    generated_at: pd.Timestamp = field(default_factory=_now_utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_label": self.session_label,
            "provider_name": self.provider_name,
            "universe_name": self.universe_name,
            "timeframe": self.timeframe,
            "requested_symbols": list(self.requested_symbols),
            "loaded_symbols": list(self.loaded_symbols),
            "ranked_symbols": list(self.ranked_symbols),
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass
class SessionSignalReport:
    enabled: bool
    provider_name: str
    timeframe: str
    session_label: str = ""
    universe_name: str = ""
    generated_at: pd.Timestamp = field(default_factory=_now_utc)

    watchlist_state: Optional[WatchlistState] = None
    market_snapshots: list[LiveMarketSnapshot] = field(default_factory=list)
    regime_snapshots: list[dict[str, Any]] = field(default_factory=list)
    relative_strength_rows: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[SignalDecision] = field(default_factory=list)

    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    exports: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def actionable_signals(self) -> list[SignalDecision]:
        return [d for d in self.decisions if d.decision_type == "actionable_signal"]

    @property
    def no_trade_decisions(self) -> list[SignalDecision]:
        return [d for d in self.decisions if d.decision_type == "no_trade"]

    @property
    def risk_rejections(self) -> list[SignalDecision]:
        return [d for d in self.decisions if d.decision_type == "risk_rejected"]

    @property
    def paper_handoff_decisions(self) -> list[SignalDecision]:
        return [d for d in self.decisions if d.paper_handoff_eligible]

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider_name": self.provider_name,
            "timeframe": self.timeframe,
            "session_label": self.session_label,
            "universe_name": self.universe_name,
            "generated_at": self.generated_at.isoformat(),
            "watchlist_state": self.watchlist_state.to_dict() if self.watchlist_state else None,
            "market_snapshots": [m.to_dict() for m in self.market_snapshots],
            "regime_snapshots": list(self.regime_snapshots),
            "relative_strength_rows": list(self.relative_strength_rows),
            "decisions": [d.to_dict() for d in self.decisions],
            "summary": {
                "symbols_loaded": len(self.market_snapshots),
                "actionable_signals": len(self.actionable_signals),
                "no_trade_decisions": len(self.no_trade_decisions),
                "risk_rejections": len(self.risk_rejections),
                "paper_handoff_eligible": len(self.paper_handoff_decisions),
            },
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "exports": dict(self.exports),
            "metadata": dict(self.metadata),
        }
