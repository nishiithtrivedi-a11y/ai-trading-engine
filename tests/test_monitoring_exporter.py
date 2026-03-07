from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.monitoring.config import MonitoringExportConfig
from src.monitoring.exporter import MonitoringExporter
from src.monitoring.models import (
    Alert,
    AlertSeverity,
    MarketSnapshot,
    MonitoringRunResult,
    RegimeAssessment,
    RegimeState,
    RelativeStrengthSnapshot,
    TopPick,
)
from src.scanners.models import Opportunity, OpportunityClass, ScanResult


def _sample_run_result() -> MonitoringRunResult:
    ts = pd.Timestamp("2026-03-07 09:15:00", tz="UTC")
    scan = ScanResult(
        opportunities=[
            Opportunity(
                symbol="RELIANCE.NS",
                timeframe="1D",
                strategy_name="SMACrossoverStrategy",
                signal="buy",
                timestamp=ts,
                classification=OpportunityClass.POSITIONAL,
                entry_price=2500.0,
                stop_loss=2450.0,
                target_price=2600.0,
                score=82.0,
            )
        ],
        num_symbols_scanned=1,
        num_jobs=1,
    )

    snapshot = MarketSnapshot(
        top_picks=[
            TopPick(
                symbol="RELIANCE.NS",
                timeframe="1D",
                strategy_name="SMACrossoverStrategy",
                timestamp=ts,
                entry_price=2500.0,
                stop_loss=2450.0,
                target_price=2600.0,
                score=82.0,
                horizon="positional",
            )
        ]
    )

    return MonitoringRunResult(
        scan_result=scan,
        regime_assessment=RegimeAssessment(regime=RegimeState.BULLISH),
        relative_strength=[RelativeStrengthSnapshot(symbol="RELIANCE.NS", score=0.72, rank=1)],
        alerts=[
            Alert(
                rule_id="new_actionable_opportunity",
                symbol="RELIANCE.NS",
                title="Actionable opportunity",
                message="RELIANCE score crossed threshold",
                severity=AlertSeverity.WARNING,
            )
        ],
        snapshot=snapshot,
    )


def test_export_all_writes_expected_files(tmp_path: Path) -> None:
    out_dir = tmp_path / "monitoring"
    cfg = MonitoringExportConfig(output_dir=str(out_dir), write_csv=True, write_json=True)
    result = _sample_run_result()

    outputs = MonitoringExporter().export_all(result, cfg)

    expected_keys = {
        "alerts_csv",
        "top_picks_csv",
        "relative_strength_csv",
        "alerts_json",
        "market_snapshot_json",
        "relative_strength_json",
        "regime_summary_json",
        "manifest_json",
    }
    assert expected_keys.issubset(set(outputs.keys()))
    for path in outputs.values():
        assert Path(path).exists()

    manifest = json.loads((out_dir / cfg.manifest_json_filename).read_text(encoding="utf-8"))
    assert "scan" in manifest
    assert "snapshot" in manifest


def test_export_empty_run_result(tmp_path: Path) -> None:
    out_dir = tmp_path / "monitoring_empty"
    cfg = MonitoringExportConfig(output_dir=str(out_dir), write_csv=True, write_json=True)
    result = MonitoringRunResult()

    outputs = MonitoringExporter().export_all(result, cfg)
    assert (out_dir / cfg.alerts_csv_filename).exists()
    assert (out_dir / cfg.manifest_json_filename).exists()
    assert len(outputs) >= 2
