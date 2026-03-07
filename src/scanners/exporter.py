"""
Scan result exporters for CSV/JSON outputs.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.scanners.config import ExportConfig
from src.scanners.models import ScanResult


class ScanExporter:
    def export_csv(self, scan_result: ScanResult, path: str | Path, top_n: int | None = None) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        df = scan_result.to_dataframe(top_n=top_n)
        df.to_csv(output_path, index=False)
        return output_path

    def export_json(self, scan_result: ScanResult, path: str | Path, top_n: int | None = None) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        payload = scan_result.to_dict(top_n=top_n)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)

        return output_path

    def export_all(
        self,
        scan_result: ScanResult,
        export_config: ExportConfig,
        top_n: int | None = None,
    ) -> dict[str, Path]:
        out_dir = Path(export_config.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        outputs: dict[str, Path] = {}

        if export_config.write_csv:
            csv_path = out_dir / export_config.csv_filename
            outputs["csv"] = self.export_csv(scan_result, csv_path, top_n=top_n)

        if export_config.write_json:
            json_path = out_dir / export_config.json_filename
            outputs["json"] = self.export_json(scan_result, json_path, top_n=top_n)

        return outputs
