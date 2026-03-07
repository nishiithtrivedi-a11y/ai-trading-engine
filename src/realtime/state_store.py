"""
In-memory state store for realtime engine runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from src.decision.models import PickRunResult
from src.monitoring.models import MonitoringRunResult
from src.realtime.models import (
    PollResult,
    RealTimeCycleResult,
    RealTimeEngineStatus,
    RealTimeSnapshot,
    RealtimeAlertRecord,
)
from src.scanners.models import ScanResult


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


@dataclass
class RealTimeStateStore:
    max_history: int = 200
    engine_status: RealTimeEngineStatus = RealTimeEngineStatus.IDLE
    started_at: Optional[pd.Timestamp] = None
    stopped_at: Optional[pd.Timestamp] = None
    updated_at: pd.Timestamp = field(default_factory=_now_utc)

    latest_poll_result: Optional[PollResult] = None
    latest_scan_result: Optional[ScanResult] = None
    latest_monitoring_result: Optional[MonitoringRunResult] = None
    latest_pick_result: Optional[PickRunResult] = None
    latest_snapshot: Optional[RealTimeSnapshot] = None
    latest_alerts: list[RealtimeAlertRecord] = field(default_factory=list)
    cycle_history: list[RealTimeCycleResult] = field(default_factory=list)

    def mark_started(self) -> None:
        self.engine_status = RealTimeEngineStatus.RUNNING
        self.started_at = _now_utc()
        self.stopped_at = None
        self.updated_at = self.started_at

    def mark_stopped(self) -> None:
        self.engine_status = RealTimeEngineStatus.STOPPED
        self.stopped_at = _now_utc()
        self.updated_at = self.stopped_at

    def mark_disabled(self) -> None:
        self.engine_status = RealTimeEngineStatus.DISABLED
        self.updated_at = _now_utc()

    def mark_error(self) -> None:
        self.engine_status = RealTimeEngineStatus.ERROR
        self.updated_at = _now_utc()

    def update_results(
        self,
        poll_result: Optional[PollResult] = None,
        scan_result: Optional[ScanResult] = None,
        monitoring_result: Optional[MonitoringRunResult] = None,
        pick_result: Optional[PickRunResult] = None,
        snapshot: Optional[RealTimeSnapshot] = None,
        alerts: Optional[list[RealtimeAlertRecord]] = None,
    ) -> None:
        if poll_result is not None:
            self.latest_poll_result = poll_result
        if scan_result is not None:
            self.latest_scan_result = scan_result
        if monitoring_result is not None:
            self.latest_monitoring_result = monitoring_result
        if pick_result is not None:
            self.latest_pick_result = pick_result
        if snapshot is not None:
            self.latest_snapshot = snapshot
        if alerts is not None:
            self.latest_alerts = list(alerts)
        self.updated_at = _now_utc()

    def record_cycle(self, cycle_result: RealTimeCycleResult) -> None:
        self.cycle_history.append(cycle_result)
        if len(self.cycle_history) > self.max_history:
            self.cycle_history = self.cycle_history[-self.max_history :]
        self.updated_at = _now_utc()

    def status(self) -> dict[str, Any]:
        return {
            "engine_status": self.engine_status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "updated_at": self.updated_at.isoformat(),
            "cycle_history_size": len(self.cycle_history),
            "latest_alerts": len(self.latest_alerts),
            "has_snapshot": self.latest_snapshot is not None,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status(),
            "latest_poll_result": (
                self.latest_poll_result.to_dict() if self.latest_poll_result is not None else None
            ),
            "latest_scan_result": (
                self.latest_scan_result.to_dict() if self.latest_scan_result is not None else None
            ),
            "latest_monitoring_result": (
                self.latest_monitoring_result.to_dict() if self.latest_monitoring_result is not None else None
            ),
            "latest_pick_result": (
                self.latest_pick_result.to_dict() if self.latest_pick_result is not None else None
            ),
            "latest_snapshot": (
                self.latest_snapshot.to_dict() if self.latest_snapshot is not None else None
            ),
            "latest_alerts": [a.to_dict() for a in self.latest_alerts],
            "cycle_history": [c.to_dict() for c in self.cycle_history],
        }
