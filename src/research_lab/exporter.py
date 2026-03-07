"""
Exporters for Phase 7 strategy research lab outputs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.research_lab.config import ResearchLabExportConfig
from src.research_lab.models import StrategyDiscoveryResult


class ResearchLabExporter:
    def export_all(
        self,
        result: StrategyDiscoveryResult,
        config: ResearchLabExportConfig,
    ) -> dict[str, Path]:
        out_dir = Path(config.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        outputs: dict[str, Path] = {}
        if config.write_csv:
            outputs.update(self._export_csv(result, out_dir, config))
        if config.write_json:
            outputs.update(self._export_json(result, out_dir, config))
        return outputs

    def _export_csv(
        self,
        result: StrategyDiscoveryResult,
        out_dir: Path,
        config: ResearchLabExportConfig,
    ) -> dict[str, Path]:
        outputs: dict[str, Path] = {}

        scores_path = out_dir / config.strategy_scores_csv
        pd.DataFrame([s.to_dict() for s in result.strategy_scores]).to_csv(scores_path, index=False)
        outputs["strategy_scores_csv"] = scores_path

        clusters_path = out_dir / config.strategy_clusters_csv
        pd.DataFrame([c.to_dict() for c in result.strategy_clusters]).to_csv(clusters_path, index=False)
        outputs["strategy_clusters_csv"] = clusters_path

        return outputs

    def _export_json(
        self,
        result: StrategyDiscoveryResult,
        out_dir: Path,
        config: ResearchLabExportConfig,
    ) -> dict[str, Path]:
        outputs: dict[str, Path] = {}

        robustness_path = out_dir / config.robustness_reports_json
        self._write_json(robustness_path, [r.to_dict() for r in result.robustness_reports])
        outputs["robustness_reports_json"] = robustness_path

        surfaces_path = out_dir / config.parameter_surfaces_json
        self._write_json(surfaces_path, [p.to_dict() for p in result.parameter_surfaces])
        outputs["parameter_surfaces_json"] = surfaces_path

        manifest_path = out_dir / config.manifest_json
        self._write_json(manifest_path, result.to_dict())
        outputs["manifest_json"] = manifest_path

        return outputs

    @staticmethod
    def _write_json(path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
