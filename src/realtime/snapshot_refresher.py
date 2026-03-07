"""
Realtime snapshot refresher that re-runs monitoring and decision pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.decision.config import DecisionConfig
from src.decision.pick_engine import PickEngine
from src.monitoring.config import MonitoringConfig
from src.monitoring.market_monitor import MarketMonitor
from src.realtime.alert_dispatcher import AlertDispatcher
from src.realtime.models import RealTimeSnapshot, SnapshotRefreshResult


class SnapshotRefresherError(Exception):
    """Raised when snapshot refresh fails."""


@dataclass
class SnapshotRefresher:
    monitoring_config: MonitoringConfig
    decision_config: DecisionConfig
    market_monitor: Optional[MarketMonitor] = None
    pick_engine: Optional[PickEngine] = None

    def __post_init__(self) -> None:
        self.market_monitor = self.market_monitor or MarketMonitor(config=self.monitoring_config)
        self.pick_engine = self.pick_engine or PickEngine(decision_config=self.decision_config)

    def refresh(
        self,
        watchlist_names: Optional[list[str]] = None,
    ) -> SnapshotRefreshResult:
        monitoring_result = self.market_monitor.run(
            export=False,
            watchlist_names=watchlist_names,
        )
        pick_result = self.pick_engine.run(
            monitoring_result=monitoring_result,
            decision_config=self.decision_config,
        )
        snapshot = self._build_snapshot(monitoring_result=monitoring_result, pick_result=pick_result)
        alerts = AlertDispatcher.from_monitoring_alerts(monitoring_result.alerts)

        return SnapshotRefreshResult(
            monitoring_result=monitoring_result,
            pick_result=pick_result,
            snapshot=snapshot,
            alerts=alerts,
            warnings=list(monitoring_result.warnings) + list(pick_result.warnings),
            errors=list(monitoring_result.errors) + list(pick_result.errors),
        )

    @staticmethod
    def _build_snapshot(
        monitoring_result,
        pick_result,
    ) -> RealTimeSnapshot:
        top = [pick.to_dict() for pick in pick_result.selected_picks]
        monitoring_summary = {
            "alerts": len(monitoring_result.alerts),
            "relative_strength_rows": len(monitoring_result.relative_strength),
            "sector_strength_rows": len(monitoring_result.sector_strength),
            "scan_opportunities": (
                len(monitoring_result.scan_result.opportunities)
                if monitoring_result.scan_result is not None
                else 0
            ),
        }
        decision_summary = {
            "selected_total": len(pick_result.selected_picks),
            "intraday_total": len(pick_result.top_intraday),
            "swing_total": len(pick_result.top_swing),
            "positional_total": len(pick_result.top_positional),
            "rejected_total": len(pick_result.rejected_opportunities),
        }
        return RealTimeSnapshot(
            monitoring_summary=monitoring_summary,
            decision_summary=decision_summary,
            top_picks=top,
            metadata={
                "regime": (
                    monitoring_result.regime_assessment.regime.value
                    if monitoring_result.regime_assessment is not None
                    else None
                )
            },
        )
