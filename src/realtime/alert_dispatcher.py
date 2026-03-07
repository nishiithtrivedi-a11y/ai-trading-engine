"""
Alert dispatch for realtime cycles (local/file based).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.monitoring.models import Alert
from src.realtime.config import RealtimeConfig
from src.realtime.models import RealtimeAlertRecord


@dataclass
class AlertDispatcher:
    dedupe_window_minutes: int = 120
    dedupe_state: dict[str, pd.Timestamp] = field(default_factory=dict)

    def dispatch(
        self,
        alerts: Iterable[RealtimeAlertRecord],
        config: RealtimeConfig,
    ) -> list[RealtimeAlertRecord]:
        if not config.enable_alert_dispatch:
            return []

        now = pd.Timestamp.now(tz="UTC")
        filtered = self._dedupe(list(alerts), now=now)

        if config.persist_alerts and filtered:
            self._persist_alerts(filtered, output_dir=config.output_dir)

        return filtered

    def _dedupe(
        self,
        alerts: list[RealtimeAlertRecord],
        now: pd.Timestamp,
    ) -> list[RealtimeAlertRecord]:
        if self.dedupe_window_minutes <= 0:
            for alert in alerts:
                key = alert.dedupe_key or alert.alert_id
                self.dedupe_state[key] = now
            return alerts

        out: list[RealtimeAlertRecord] = []
        window = pd.Timedelta(minutes=self.dedupe_window_minutes)
        for alert in alerts:
            key = alert.dedupe_key or alert.alert_id
            last_seen = self.dedupe_state.get(key)
            if last_seen is not None and (now - last_seen) < window:
                continue
            self.dedupe_state[key] = now
            out.append(alert)
        return out

    @staticmethod
    def _persist_alerts(alerts: list[RealtimeAlertRecord], output_dir: str) -> Path:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "realtime_alerts.csv"

        rows = [a.to_dict() for a in alerts]
        df = pd.DataFrame(rows)
        if path.exists():
            df.to_csv(path, mode="a", header=False, index=False)
        else:
            df.to_csv(path, index=False)
        return path

    @staticmethod
    def from_monitoring_alerts(alerts: Iterable[Alert]) -> list[RealtimeAlertRecord]:
        out: list[RealtimeAlertRecord] = []
        for alert in alerts:
            out.append(
                RealtimeAlertRecord(
                    alert_id=alert.alert_id,
                    severity=alert.severity.value,
                    title=alert.title,
                    message=alert.message,
                    timestamp=alert.timestamp,
                    symbol=alert.symbol,
                    dedupe_key=alert.dedupe_key,
                    metadata=dict(alert.metadata),
                )
            )
        return out
