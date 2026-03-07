"""
Core models for the Phase 4 market monitoring layer.

These models are intentionally explicit and serializer-friendly so they can
feed future UI and automation layers without hidden behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

import pandas as pd

from src.scanners.config import normalize_timeframe

if TYPE_CHECKING:
    from src.scanners.models import ScanResult


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        clean = str(raw).strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
    return out


class RegimeState(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGEBOUND = "rangebound"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    UNKNOWN = "unknown"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    HIGH_PRIORITY = "high_priority"


class ScheduleMode(str, Enum):
    MANUAL = "manual"
    INTERVAL = "interval"
    DAILY = "daily"


@dataclass
class WatchlistItem:
    symbol: str
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    default_timeframes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = str(self.symbol).strip().upper()
        if not self.symbol:
            raise ValueError("watchlist item symbol cannot be empty")

        self.tags = _dedupe_preserve_order([str(tag).strip().lower() for tag in self.tags])
        self.default_timeframes = _dedupe_preserve_order(
            [normalize_timeframe(tf) for tf in self.default_timeframes]
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "tags": list(self.tags),
            "notes": self.notes,
            "default_timeframes": list(self.default_timeframes),
            "metadata": dict(self.metadata),
        }


@dataclass
class Watchlist:
    name: str
    items: list[WatchlistItem] = field(default_factory=list)
    source: str = "custom"
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.name = str(self.name).strip()
        if not self.name:
            raise ValueError("watchlist name cannot be empty")

    @property
    def symbols(self) -> list[str]:
        return _dedupe_preserve_order([item.symbol for item in self.items])

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "notes": self.notes,
            "symbols": self.symbols,
            "items": [item.to_dict() for item in self.items],
            "metadata": dict(self.metadata),
        }


@dataclass
class RegimeAssessment:
    regime: RegimeState
    timestamp: pd.Timestamp = field(default_factory=_now_utc)
    trend_score: Optional[float] = None
    volatility_score: Optional[float] = None
    range_score: Optional[float] = None
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime.value,
            "timestamp": self.timestamp.isoformat(),
            "trend_score": self.trend_score,
            "volatility_score": self.volatility_score,
            "range_score": self.range_score,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


@dataclass
class RelativeStrengthSnapshot:
    symbol: str
    score: float
    lookback_returns: dict[str, float] = field(default_factory=dict)
    benchmark_symbol: Optional[str] = None
    relative_return: Optional[float] = None
    rank: Optional[int] = None
    sector: Optional[str] = None
    timestamp: pd.Timestamp = field(default_factory=_now_utc)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = str(self.symbol).strip().upper()
        if not self.symbol:
            raise ValueError("relative strength symbol cannot be empty")
        self.score = float(self.score)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "score": self.score,
            "rank": self.rank,
            "benchmark_symbol": self.benchmark_symbol,
            "relative_return": self.relative_return,
            "sector": self.sector,
            "timestamp": self.timestamp.isoformat(),
            "lookback_returns": dict(self.lookback_returns),
            "metadata": dict(self.metadata),
        }


@dataclass
class SectorStrengthSnapshot:
    sector: str
    score: float
    member_count: int
    top_symbols: list[str] = field(default_factory=list)
    rank: Optional[int] = None
    timestamp: pd.Timestamp = field(default_factory=_now_utc)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.sector = str(self.sector).strip()
        if not self.sector:
            raise ValueError("sector name cannot be empty")
        if self.member_count < 0:
            raise ValueError("member_count cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "sector": self.sector,
            "score": float(self.score),
            "member_count": int(self.member_count),
            "top_symbols": list(self.top_symbols),
            "rank": self.rank,
            "timestamp": self.timestamp.isoformat(),
            "metadata": dict(self.metadata),
        }


@dataclass
class AlertRule:
    rule_id: str
    event_type: str
    severity: AlertSeverity = AlertSeverity.INFO
    enabled: bool = True
    min_score: Optional[float] = None
    watchlist_name: Optional[str] = None
    top_n: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.rule_id = str(self.rule_id).strip()
        self.event_type = str(self.event_type).strip()
        if not self.rule_id:
            raise ValueError("rule_id cannot be empty")
        if not self.event_type:
            raise ValueError("event_type cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "event_type": self.event_type,
            "severity": self.severity.value,
            "enabled": self.enabled,
            "min_score": self.min_score,
            "watchlist_name": self.watchlist_name,
            "top_n": self.top_n,
            "metadata": dict(self.metadata),
        }


@dataclass
class Alert:
    rule_id: str
    title: str
    message: str
    severity: AlertSeverity = AlertSeverity.INFO
    timestamp: pd.Timestamp = field(default_factory=_now_utc)
    symbol: Optional[str] = None
    dedupe_key: Optional[str] = None
    alert_id: str = field(default_factory=lambda: uuid4().hex)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.symbol is not None:
            self.symbol = str(self.symbol).strip().upper()
        if not self.dedupe_key:
            symbol_part = self.symbol or "GLOBAL"
            self.dedupe_key = f"{self.rule_id}|{symbol_part}|{self.title.strip().lower()}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "rule_id": self.rule_id,
            "title": self.title,
            "message": self.message,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "dedupe_key": self.dedupe_key,
            "metadata": dict(self.metadata),
        }


@dataclass
class TopPick:
    symbol: str
    timeframe: str
    strategy_name: str
    timestamp: pd.Timestamp
    entry_price: float
    stop_loss: float
    score: float
    target_price: Optional[float] = None
    horizon: Optional[str] = None
    regime_context: Optional[str] = None
    relative_strength_score: Optional[float] = None
    watchlist_tags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = str(self.symbol).strip().upper()
        self.timeframe = normalize_timeframe(self.timeframe)
        if self.entry_price <= 0:
            raise ValueError("entry_price must be positive")
        if self.stop_loss <= 0:
            raise ValueError("stop_loss must be positive")
        self.score = float(self.score)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "strategy_name": self.strategy_name,
            "timestamp": self.timestamp.isoformat(),
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "target_price": self.target_price,
            "score": self.score,
            "horizon": self.horizon,
            "regime_context": self.regime_context,
            "relative_strength_score": self.relative_strength_score,
            "watchlist_tags": list(self.watchlist_tags),
            "reasons": list(self.reasons),
            "metadata": dict(self.metadata),
        }


@dataclass
class MarketSnapshot:
    generated_at: pd.Timestamp = field(default_factory=_now_utc)
    top_picks: list[TopPick] = field(default_factory=list)
    regime_assessment: Optional[RegimeAssessment] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "regime_assessment": (
                self.regime_assessment.to_dict() if self.regime_assessment else None
            ),
            "top_picks": [pick.to_dict() for pick in self.top_picks],
            "metadata": dict(self.metadata),
        }


@dataclass
class ScheduleSpec:
    name: str
    mode: ScheduleMode = ScheduleMode.MANUAL
    enabled: bool = False
    interval_minutes: Optional[int] = None
    daily_time: Optional[str] = None
    timezone: str = "Asia/Kolkata"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.name = str(self.name).strip()
        if not self.name:
            raise ValueError("schedule name cannot be empty")

        if self.mode == ScheduleMode.INTERVAL:
            if self.interval_minutes is None or self.interval_minutes <= 0:
                raise ValueError("interval schedule requires interval_minutes > 0")
        if self.mode == ScheduleMode.DAILY:
            if not self.daily_time:
                raise ValueError("daily schedule requires daily_time in HH:MM format")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mode": self.mode.value,
            "enabled": self.enabled,
            "interval_minutes": self.interval_minutes,
            "daily_time": self.daily_time,
            "timezone": self.timezone,
            "metadata": dict(self.metadata),
        }


@dataclass
class MonitoringRunResult:
    generated_at: pd.Timestamp = field(default_factory=_now_utc)
    scan_result: Optional["ScanResult"] = None
    regime_assessment: Optional[RegimeAssessment] = None
    relative_strength: list[RelativeStrengthSnapshot] = field(default_factory=list)
    sector_strength: list[SectorStrengthSnapshot] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    snapshot: Optional[MarketSnapshot] = None
    exports: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self, include_full_scan_result: bool = False) -> dict[str, Any]:
        scan_summary: dict[str, Any] = {}
        if self.scan_result is not None:
            scan_summary = {
                "num_symbols_scanned": self.scan_result.num_symbols_scanned,
                "num_jobs": self.scan_result.num_jobs,
                "num_errors": self.scan_result.num_errors,
                "total_opportunities": len(self.scan_result.opportunities),
            }
            if include_full_scan_result:
                scan_summary["scan_result"] = self.scan_result.to_dict()

        return {
            "generated_at": self.generated_at.isoformat(),
            "scan": scan_summary,
            "regime_assessment": (
                self.regime_assessment.to_dict() if self.regime_assessment else None
            ),
            "relative_strength": [row.to_dict() for row in self.relative_strength],
            "sector_strength": [row.to_dict() for row in self.sector_strength],
            "alerts": [alert.to_dict() for alert in self.alerts],
            "snapshot": self.snapshot.to_dict() if self.snapshot else None,
            "exports": dict(self.exports),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }
