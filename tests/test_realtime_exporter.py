from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.realtime.config import RealtimeConfig
from src.realtime.exporter import RealTimeExporter
from src.realtime.models import (
    RealTimeCycleResult,
    RealTimeCycleStatus,
    RealTimeEngineStatus,
    RealTimeMode,
    RealTimeRunResult,
    RealTimeSnapshot,
    RealtimeAlertRecord,
)


def _sample_run_result() -> RealTimeRunResult:
    snapshot = RealTimeSnapshot(top_picks=[{"symbol": "RELIANCE.NS"}])
    alert = RealtimeAlertRecord(
        alert_id="a1",
        severity="warning",
        title="Actionable",
        message="RELIANCE buy",
        timestamp=pd.Timestamp("2026-03-07T10:00:00Z"),
        symbol="RELIANCE.NS",
    )
    cycle = RealTimeCycleResult(
        cycle_id=1,
        status=RealTimeCycleStatus.COMPLETED,
        completed_at=pd.Timestamp("2026-03-07T10:00:10Z"),
        snapshot=snapshot,
        alerts=[alert],
    )
    return RealTimeRunResult(
        status=RealTimeEngineStatus.STOPPED,
        enabled=True,
        mode=RealTimeMode.SIMULATED,
        completed_at=pd.Timestamp("2026-03-07T10:01:00Z"),
        cycle_results=[cycle],
    )


def test_realtime_exporter_writes_expected_files(tmp_path: Path) -> None:
    exporter = RealTimeExporter()
    cfg = RealtimeConfig(
        enabled=True,
        mode=RealTimeMode.SIMULATED,
        output_dir=str(tmp_path),
        persist_snapshots=True,
        persist_alerts=True,
    )

    out = exporter.export_all(_sample_run_result(), cfg)
    assert (tmp_path / "realtime_status.json").exists()
    assert (tmp_path / "realtime_cycle_history.csv").exists()
    assert (tmp_path / "realtime_snapshot.json").exists()
    assert (tmp_path / "realtime_alerts.csv").exists()
    assert (tmp_path / "realtime_manifest.json").exists()
    assert "realtime_manifest_json" in out


def test_realtime_exporter_respects_persistence_switches(tmp_path: Path) -> None:
    exporter = RealTimeExporter()
    cfg = RealtimeConfig(
        enabled=True,
        mode=RealTimeMode.SIMULATED,
        output_dir=str(tmp_path),
        persist_snapshots=False,
        persist_alerts=False,
    )
    exporter.export_all(_sample_run_result(), cfg)
    assert not (tmp_path / "realtime_snapshot.json").exists()
    assert not (tmp_path / "realtime_alerts.csv").exists()
