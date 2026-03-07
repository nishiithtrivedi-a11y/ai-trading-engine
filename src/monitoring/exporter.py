"""
Exporters for Phase 4 monitoring outputs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.monitoring.config import MonitoringExportConfig
from src.monitoring.models import MonitoringRunResult


class MonitoringExporter:
    def export_all(
        self,
        run_result: MonitoringRunResult,
        export_config: MonitoringExportConfig,
    ) -> dict[str, Path]:
        out_dir = Path(export_config.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        outputs: dict[str, Path] = {}

        if export_config.write_csv:
            outputs.update(self._export_csv_outputs(run_result, out_dir, export_config))

        if export_config.write_json:
            outputs.update(self._export_json_outputs(run_result, out_dir, export_config))

        return outputs

    def _export_csv_outputs(
        self,
        run_result: MonitoringRunResult,
        out_dir: Path,
        cfg: MonitoringExportConfig,
    ) -> dict[str, Path]:
        outputs: dict[str, Path] = {}

        alerts_df = pd.DataFrame([a.to_dict() for a in run_result.alerts])
        alerts_path = out_dir / cfg.alerts_csv_filename
        alerts_df.to_csv(alerts_path, index=False)
        outputs["alerts_csv"] = alerts_path

        picks = run_result.snapshot.top_picks if run_result.snapshot else []
        picks_df = pd.DataFrame([p.to_dict() for p in picks])
        picks_path = out_dir / cfg.top_picks_csv_filename
        picks_df.to_csv(picks_path, index=False)
        outputs["top_picks_csv"] = picks_path

        rs_df = pd.DataFrame([row.to_dict() for row in run_result.relative_strength])
        rs_path = out_dir / cfg.relative_strength_csv_filename
        rs_df.to_csv(rs_path, index=False)
        outputs["relative_strength_csv"] = rs_path

        return outputs

    def _export_json_outputs(
        self,
        run_result: MonitoringRunResult,
        out_dir: Path,
        cfg: MonitoringExportConfig,
    ) -> dict[str, Path]:
        outputs: dict[str, Path] = {}

        alerts_json_path = out_dir / cfg.alerts_json_filename
        self._write_json(alerts_json_path, [a.to_dict() for a in run_result.alerts])
        outputs["alerts_json"] = alerts_json_path

        snapshot_json_path = out_dir / cfg.market_snapshot_json_filename
        snapshot_payload = run_result.snapshot.to_dict() if run_result.snapshot else {}
        self._write_json(snapshot_json_path, snapshot_payload)
        outputs["market_snapshot_json"] = snapshot_json_path

        rs_json_path = out_dir / cfg.relative_strength_json_filename
        self._write_json(rs_json_path, [row.to_dict() for row in run_result.relative_strength])
        outputs["relative_strength_json"] = rs_json_path

        regime_json_path = out_dir / cfg.regime_summary_json_filename
        regime_payload = run_result.regime_assessment.to_dict() if run_result.regime_assessment else {}
        self._write_json(regime_json_path, regime_payload)
        outputs["regime_summary_json"] = regime_json_path

        manifest_path = out_dir / cfg.manifest_json_filename
        self._write_json(manifest_path, run_result.to_dict(include_full_scan_result=False))
        outputs["manifest_json"] = manifest_path

        return outputs

    @staticmethod
    def _write_json(path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
