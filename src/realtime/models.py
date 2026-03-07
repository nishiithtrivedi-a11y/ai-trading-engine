"""
Core models for the Phase 8 real-time market engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

import pandas as pd

if TYPE_CHECKING:
    from src.decision.models import PickRunResult
    from src.monitoring.models import MonitoringRunResult


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


class RealTimeMode(str, Enum):
    OFF = "off"
    SIMULATED = "simulated"
    POLLING = "polling"


class RealTimeEngineStatus(str, Enum):
    DISABLED = "disabled"
    IDLE = "idle"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class RealTimeCycleStatus(str, Enum):
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class PolledSymbolData:
    symbol: str
    timeframe: str
    timestamp: Optional[pd.Timestamp]
    close_price: Optional[float]
    bars: int
    source: str
    success: bool = True
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp.isoformat() if self.timestamp is not None else None,
            "close_price": self.close_price,
            "bars": self.bars,
            "source": self.source,
            "success": self.success,
            "message": self.message,
            "metadata": dict(self.metadata),
        }


@dataclass
class PollResult:
    generated_at: pd.Timestamp = field(default_factory=_now_utc)
    mode: RealTimeMode = RealTimeMode.OFF
    records: list[PolledSymbolData] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "mode": self.mode.value,
            "record_count": len(self.records),
            "records": [r.to_dict() for r in self.records],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


@dataclass
class RealTimeSnapshot:
    generated_at: pd.Timestamp = field(default_factory=_now_utc)
    monitoring_summary: dict[str, Any] = field(default_factory=dict)
    decision_summary: dict[str, Any] = field(default_factory=dict)
    top_picks: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "monitoring_summary": dict(self.monitoring_summary),
            "decision_summary": dict(self.decision_summary),
            "top_picks": list(self.top_picks),
            "metadata": dict(self.metadata),
        }


@dataclass
class SnapshotRefreshResult:
    monitoring_result: "MonitoringRunResult"
    pick_result: "PickRunResult"
    snapshot: RealTimeSnapshot
    alerts: list["RealtimeAlertRecord"] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "monitoring_result": self.monitoring_result.to_dict(),
            "pick_result": self.pick_result.to_dict(),
            "snapshot": self.snapshot.to_dict(),
            "alerts": [a.to_dict() for a in self.alerts],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


@dataclass
class RealtimeAlertRecord:
    alert_id: str
    severity: str
    title: str
    message: str
    timestamp: pd.Timestamp = field(default_factory=_now_utc)
    symbol: Optional[str] = None
    dedupe_key: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "dedupe_key": self.dedupe_key,
            "metadata": dict(self.metadata),
        }


@dataclass
class RealTimeCycleResult:
    cycle_id: int
    started_at: pd.Timestamp = field(default_factory=_now_utc)
    completed_at: Optional[pd.Timestamp] = None
    status: RealTimeCycleStatus = RealTimeCycleStatus.SKIPPED
    market_open: Optional[bool] = None
    skipped_reason: str = ""
    poll_result: Optional[PollResult] = None
    snapshot: Optional[RealTimeSnapshot] = None
    alerts: list[RealtimeAlertRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.completed_at is None:
            return None
        return float((self.completed_at - self.started_at).total_seconds())

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at is not None else None,
            "duration_seconds": self.duration_seconds,
            "status": self.status.value,
            "market_open": self.market_open,
            "skipped_reason": self.skipped_reason,
            "poll_result": self.poll_result.to_dict() if self.poll_result else None,
            "snapshot": self.snapshot.to_dict() if self.snapshot else None,
            "alerts": [a.to_dict() for a in self.alerts],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "metadata": dict(self.metadata),
        }


@dataclass
class RealTimeRunResult:
    started_at: pd.Timestamp = field(default_factory=_now_utc)
    completed_at: Optional[pd.Timestamp] = None
    status: RealTimeEngineStatus = RealTimeEngineStatus.IDLE
    enabled: bool = False
    mode: RealTimeMode = RealTimeMode.OFF
    cycle_results: list[RealTimeCycleResult] = field(default_factory=list)
    exports: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_cycles(self) -> int:
        return len(self.cycle_results)

    @property
    def completed_cycles(self) -> int:
        return sum(1 for c in self.cycle_results if c.status == RealTimeCycleStatus.COMPLETED)

    @property
    def skipped_cycles(self) -> int:
        return sum(1 for c in self.cycle_results if c.status == RealTimeCycleStatus.SKIPPED)

    @property
    def failed_cycles(self) -> int:
        return sum(1 for c in self.cycle_results if c.status == RealTimeCycleStatus.FAILED)

    @property
    def last_snapshot(self) -> Optional[RealTimeSnapshot]:
        for cycle in reversed(self.cycle_results):
            if cycle.snapshot is not None:
                return cycle.snapshot
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at is not None else None,
            "status": self.status.value,
            "enabled": self.enabled,
            "mode": self.mode.value,
            "summary": {
                "total_cycles": self.total_cycles,
                "completed_cycles": self.completed_cycles,
                "skipped_cycles": self.skipped_cycles,
                "failed_cycles": self.failed_cycles,
            },
            "cycle_results": [c.to_dict() for c in self.cycle_results],
            "last_snapshot": self.last_snapshot.to_dict() if self.last_snapshot else None,
            "exports": dict(self.exports),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "metadata": dict(self.metadata),
        }
