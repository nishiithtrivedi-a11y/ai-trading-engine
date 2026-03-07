from __future__ import annotations

import pandas as pd

from src.decision.models import PickRunResult
from src.monitoring.models import MonitoringRunResult
from src.realtime.models import (
    PollResult,
    RealTimeCycleResult,
    RealTimeCycleStatus,
    RealTimeEngineStatus,
    RealTimeSnapshot,
    RealtimeAlertRecord,
)
from src.realtime.state_store import RealTimeStateStore
from src.scanners.models import ScanResult


def test_state_store_status_transitions() -> None:
    store = RealTimeStateStore()
    assert store.engine_status == RealTimeEngineStatus.IDLE

    store.mark_started()
    assert store.engine_status == RealTimeEngineStatus.RUNNING
    assert store.started_at is not None

    store.mark_stopped()
    assert store.engine_status == RealTimeEngineStatus.STOPPED
    assert store.stopped_at is not None


def test_state_store_updates_latest_results() -> None:
    store = RealTimeStateStore()

    poll = PollResult()
    scan = ScanResult()
    monitoring = MonitoringRunResult()
    picks = PickRunResult()
    snapshot = RealTimeSnapshot(top_picks=[{"symbol": "RELIANCE.NS"}])
    alerts = [
        RealtimeAlertRecord(
            alert_id="a1",
            severity="info",
            title="t",
            message="m",
            timestamp=pd.Timestamp("2026-03-07T10:00:00Z"),
        )
    ]

    store.update_results(
        poll_result=poll,
        scan_result=scan,
        monitoring_result=monitoring,
        pick_result=picks,
        snapshot=snapshot,
        alerts=alerts,
    )

    assert store.latest_poll_result is poll
    assert store.latest_scan_result is scan
    assert store.latest_monitoring_result is monitoring
    assert store.latest_pick_result is picks
    assert store.latest_snapshot is snapshot
    assert len(store.latest_alerts) == 1


def test_state_store_cycle_history_respects_max_history() -> None:
    store = RealTimeStateStore(max_history=2)
    for i in range(5):
        cycle = RealTimeCycleResult(cycle_id=i + 1, status=RealTimeCycleStatus.COMPLETED)
        store.record_cycle(cycle)

    assert len(store.cycle_history) == 2
    assert store.cycle_history[0].cycle_id == 4
    assert store.cycle_history[1].cycle_id == 5
