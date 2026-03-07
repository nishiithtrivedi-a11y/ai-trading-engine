from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.scanners.config import ExportConfig
from src.scanners.exporter import ScanExporter
from src.scanners.models import Opportunity, OpportunityClass, ScanResult


def _sample_result() -> ScanResult:
    opp = Opportunity(
        symbol="RELIANCE.NS",
        timeframe="1D",
        strategy_name="Dummy",
        signal="buy",
        timestamp=pd.Timestamp("2026-03-01"),
        classification=OpportunityClass.POSITIONAL,
        entry_price=100.0,
        stop_loss=98.0,
        target_price=104.0,
        score=75.0,
    )
    return ScanResult(opportunities=[opp], universe_name="custom", provider_name="csv")


def test_csv_export(tmp_path: Path) -> None:
    exporter = ScanExporter()
    result = _sample_result()

    out = exporter.export_csv(result, tmp_path / "out" / "scan.csv")

    assert out.exists()
    df = pd.read_csv(out)
    assert len(df) == 1
    assert "symbol" in df.columns


def test_json_export(tmp_path: Path) -> None:
    exporter = ScanExporter()
    result = _sample_result()

    out = exporter.export_json(result, tmp_path / "out" / "scan.json")

    assert out.exists()
    with open(out, encoding="utf-8") as f:
        payload = json.load(f)

    assert "opportunities" in payload
    assert len(payload["opportunities"]) == 1


def test_empty_scan_result_export(tmp_path: Path) -> None:
    exporter = ScanExporter()
    result = ScanResult(opportunities=[])

    csv_out = exporter.export_csv(result, tmp_path / "empty" / "empty.csv")
    json_out = exporter.export_json(result, tmp_path / "empty" / "empty.json")

    assert csv_out.exists()
    assert json_out.exists()

    with open(json_out, encoding="utf-8") as f:
        payload = json.load(f)
    assert payload["opportunities"] == []


def test_export_all_creates_output_directory(tmp_path: Path) -> None:
    exporter = ScanExporter()
    result = _sample_result()

    cfg = ExportConfig(
        output_dir=str(tmp_path / "nested" / "scanner_out"),
        csv_filename="ops.csv",
        json_filename="ops.json",
        write_csv=True,
        write_json=True,
    )

    outputs = exporter.export_all(result, cfg, top_n=10)

    assert (tmp_path / "nested" / "scanner_out").exists()
    assert outputs["csv"].name == "ops.csv"
    assert outputs["json"].name == "ops.json"
    assert outputs["csv"].exists()
    assert outputs["json"].exists()
