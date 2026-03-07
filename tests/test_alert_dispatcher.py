from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.realtime.alert_dispatcher import AlertDispatcher
from src.realtime.config import RealtimeConfig
from src.realtime.models import RealTimeMode, RealtimeAlertRecord


def _alert(alert_id: str, dedupe_key: str) -> RealtimeAlertRecord:
    return RealtimeAlertRecord(
        alert_id=alert_id,
        severity="warning",
        title="Actionable",
        message="Test alert",
        timestamp=pd.Timestamp("2026-03-07T10:00:00Z"),
        symbol="RELIANCE.NS",
        dedupe_key=dedupe_key,
    )


def test_dispatch_disabled_returns_empty() -> None:
    dispatcher = AlertDispatcher()
    cfg = RealtimeConfig(
        enabled=True,
        mode=RealTimeMode.SIMULATED,
        enable_alert_dispatch=False,
    )
    out = dispatcher.dispatch([_alert("a1", "k1")], cfg)
    assert out == []


def test_dispatch_deduplicates_within_window() -> None:
    dispatcher = AlertDispatcher(dedupe_window_minutes=60)
    cfg = RealtimeConfig(enabled=True, mode=RealTimeMode.SIMULATED)
    first = dispatcher.dispatch([_alert("a1", "dup")], cfg)
    second = dispatcher.dispatch([_alert("a2", "dup")], cfg)
    assert len(first) == 1
    assert len(second) == 0


def test_dispatch_persists_alerts(tmp_path: Path) -> None:
    dispatcher = AlertDispatcher(dedupe_window_minutes=0)
    cfg = RealtimeConfig(
        enabled=True,
        mode=RealTimeMode.SIMULATED,
        output_dir=str(tmp_path),
        persist_alerts=True,
    )
    out = dispatcher.dispatch([_alert("a1", "k1")], cfg)
    assert len(out) == 1
    path = tmp_path / "realtime_alerts.csv"
    assert path.exists()
