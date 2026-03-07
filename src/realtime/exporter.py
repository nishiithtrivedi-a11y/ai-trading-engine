"""
Exporters for realtime engine outputs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.realtime.config import RealtimeConfig
from src.realtime.models import RealTimeRunResult


class RealTimeExporter:
    def export_all(
        self,
        run_result: RealTimeRunResult,
        config: RealtimeConfig,
    ) -> dict[str, Path]:
        out_dir = Path(config.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        outputs: dict[str, Path] = {}
        outputs["realtime_status_json"] = self._write_json(
            out_dir / "realtime_status.json",
            {
                "status": run_result.status.value,
                "enabled": run_result.enabled,
                "mode": run_result.mode.value,
                "started_at": run_result.started_at.isoformat(),
                "completed_at": run_result.completed_at.isoformat() if run_result.completed_at else None,
                "summary": {
                    "total_cycles": run_result.total_cycles,
                    "completed_cycles": run_result.completed_cycles,
                    "skipped_cycles": run_result.skipped_cycles,
                    "failed_cycles": run_result.failed_cycles,
                },
                "warnings": list(run_result.warnings),
                "errors": list(run_result.errors),
            },
        )

        cycle_history_path = out_dir / "realtime_cycle_history.csv"
        cycle_rows = [c.to_dict() for c in run_result.cycle_results]
        pd.DataFrame(cycle_rows).to_csv(cycle_history_path, index=False)
        outputs["realtime_cycle_history_csv"] = cycle_history_path

        if config.persist_snapshots:
            snapshot_path = out_dir / "realtime_snapshot.json"
            snapshot_payload = run_result.last_snapshot.to_dict() if run_result.last_snapshot else {}
            outputs["realtime_snapshot_json"] = self._write_json(snapshot_path, snapshot_payload)

        if config.persist_alerts:
            alerts_path = out_dir / "realtime_alerts.csv"
            alert_rows = []
            for cycle in run_result.cycle_results:
                alert_rows.extend(a.to_dict() for a in cycle.alerts)
            pd.DataFrame(alert_rows).to_csv(alerts_path, index=False)
            outputs["realtime_alerts_csv"] = alerts_path

        outputs["realtime_manifest_json"] = self._write_json(
            out_dir / "realtime_manifest.json",
            run_result.to_dict(),
        )

        return outputs

    @staticmethod
    def _write_json(path: Path, payload) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, default=str)
        return path
