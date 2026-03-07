from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.decision.config import DecisionConfig
from src.monitoring.config import MonitoringConfig
from src.monitoring.models import Alert, AlertSeverity, MonitoringRunResult
from src.realtime.snapshot_refresher import SnapshotRefresher


class _FakePick:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def to_dict(self) -> dict:
        return {"symbol": self.symbol, "conviction_score": 80.0}


@dataclass
class _FakePickResult:
    selected_picks: list = field(default_factory=list)
    top_intraday: list = field(default_factory=list)
    top_swing: list = field(default_factory=list)
    top_positional: list = field(default_factory=list)
    rejected_opportunities: list = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class _FakeMarketMonitor:
    def __init__(self, result: MonitoringRunResult) -> None:
        self._result = result

    def run(self, export: bool = False, watchlist_names=None) -> MonitoringRunResult:
        return self._result


class _FakePickEngine:
    def __init__(self, result: _FakePickResult) -> None:
        self._result = result

    def run(self, monitoring_result=None, decision_config=None):
        return self._result


def test_snapshot_refresher_builds_snapshot_and_converts_alerts() -> None:
    monitoring = MonitoringRunResult(
        alerts=[
            Alert(
                rule_id="r1",
                title="Actionable opportunity",
                message="RELIANCE buy",
                severity=AlertSeverity.WARNING,
                timestamp=pd.Timestamp("2026-03-07T10:00:00Z"),
                symbol="RELIANCE.NS",
            )
        ]
    )
    picks = _FakePickResult(
        selected_picks=[_FakePick("RELIANCE.NS"), _FakePick("TCS.NS")],
        top_intraday=[_FakePick("RELIANCE.NS")],
    )

    refresher = SnapshotRefresher(
        monitoring_config=MonitoringConfig(),
        decision_config=DecisionConfig(),
        market_monitor=_FakeMarketMonitor(monitoring),
        pick_engine=_FakePickEngine(picks),
    )

    out = refresher.refresh()
    assert len(out.snapshot.top_picks) == 2
    assert out.snapshot.decision_summary["selected_total"] == 2
    assert len(out.alerts) == 1
    assert out.alerts[0].symbol == "RELIANCE.NS"
