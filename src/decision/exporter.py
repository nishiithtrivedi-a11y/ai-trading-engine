"""
Exporter utilities for Phase 5 decision outputs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.decision.config import DecisionExportConfig
from src.decision.models import PickRunResult


class DecisionExporter:
    def export_all(
        self,
        result: PickRunResult,
        export_config: DecisionExportConfig,
    ) -> dict[str, Path]:
        out_dir = Path(export_config.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        outputs: dict[str, Path] = {}
        if export_config.write_csv:
            outputs.update(self._export_csv(result, out_dir, export_config))
        if export_config.write_json:
            outputs.update(self._export_json(result, out_dir, export_config))
        return outputs

    def _export_csv(
        self,
        result: PickRunResult,
        out_dir: Path,
        cfg: DecisionExportConfig,
    ) -> dict[str, Path]:
        outputs: dict[str, Path] = {}

        intraday_path = out_dir / cfg.intraday_csv_filename
        pd.DataFrame([p.to_dict() for p in result.top_intraday]).to_csv(intraday_path, index=False)
        outputs["intraday_csv"] = intraday_path

        swing_path = out_dir / cfg.swing_csv_filename
        pd.DataFrame([p.to_dict() for p in result.top_swing]).to_csv(swing_path, index=False)
        outputs["swing_csv"] = swing_path

        positional_path = out_dir / cfg.positional_csv_filename
        pd.DataFrame([p.to_dict() for p in result.top_positional]).to_csv(positional_path, index=False)
        outputs["positional_csv"] = positional_path

        rejected_path = out_dir / cfg.rejected_csv_filename
        pd.DataFrame([r.to_dict() for r in result.rejected_opportunities]).to_csv(
            rejected_path, index=False
        )
        outputs["rejected_csv"] = rejected_path

        return outputs

    def _export_json(
        self,
        result: PickRunResult,
        out_dir: Path,
        cfg: DecisionExportConfig,
    ) -> dict[str, Path]:
        outputs: dict[str, Path] = {}

        summary_payload = {
            "generated_at": result.generated_at.isoformat(),
            "summary": result.to_dict()["summary"],
            "top_intraday_symbols": [p.symbol for p in result.top_intraday],
            "top_swing_symbols": [p.symbol for p in result.top_swing],
            "top_positional_symbols": [p.symbol for p in result.top_positional],
            "warnings": result.warnings,
            "errors": result.errors,
        }

        summary_path = out_dir / cfg.summary_json_filename
        self._write_json(summary_path, summary_payload)
        outputs["summary_json"] = summary_path

        manifest_path = out_dir / cfg.manifest_json_filename
        self._write_json(manifest_path, result.to_dict())
        outputs["manifest_json"] = manifest_path

        return outputs

    @staticmethod
    def _write_json(path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
