"""
Exporters for Phase 6 market intelligence outputs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.market_intelligence.config import MarketIntelligenceExportConfig
from src.market_intelligence.models import MarketIntelligenceResult


class MarketIntelligenceExporter:
    def export_all(
        self,
        result: MarketIntelligenceResult,
        config: MarketIntelligenceExportConfig,
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
        result: MarketIntelligenceResult,
        out_dir: Path,
        config: MarketIntelligenceExportConfig,
    ) -> dict[str, Path]:
        outputs: dict[str, Path] = {}

        breadth_path = out_dir / config.market_breadth_csv
        breadth_row = [result.breadth_snapshot.to_dict()] if result.breadth_snapshot else []
        pd.DataFrame(breadth_row).to_csv(breadth_path, index=False)
        outputs["market_breadth_csv"] = breadth_path

        sector_path = out_dir / config.sector_rotation_csv
        pd.DataFrame([row.to_dict() for row in result.sector_rotation]).to_csv(sector_path, index=False)
        outputs["sector_rotation_csv"] = sector_path

        volume_rows = []
        for snapshot in result.volume_analysis:
            for signal in snapshot.signals:
                row = signal.to_dict()
                row["timeframe"] = snapshot.timeframe
                volume_rows.append(row)
        volume_path = out_dir / config.volume_signals_csv
        pd.DataFrame(volume_rows).to_csv(volume_path, index=False)
        outputs["volume_signals_csv"] = volume_path

        return outputs

    def _export_json(
        self,
        result: MarketIntelligenceResult,
        out_dir: Path,
        config: MarketIntelligenceExportConfig,
    ) -> dict[str, Path]:
        outputs: dict[str, Path] = {}

        vol_path = out_dir / config.volatility_regime_json
        self._write_json(
            vol_path,
            result.volatility_snapshot.to_dict() if result.volatility_snapshot else {},
        )
        outputs["volatility_regime_json"] = vol_path

        state_path = out_dir / config.market_state_summary_json
        self._write_json(
            state_path,
            {
                "market_state": result.market_state.to_dict() if result.market_state else None,
                "institutional_flow": (
                    result.institutional_flow.to_dict() if result.institutional_flow else None
                ),
            },
        )
        outputs["market_state_summary_json"] = state_path

        manifest_path = out_dir / config.manifest_json
        self._write_json(manifest_path, result.to_dict())
        outputs["manifest_json"] = manifest_path

        return outputs

    @staticmethod
    def _write_json(path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
