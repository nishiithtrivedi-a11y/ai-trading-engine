from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from scripts import run_decision, run_monitoring, run_scanner


def _write_symbol_csv(data_dir: Path, symbol: str, *, base: float, slope: float) -> None:
    stem = symbol.replace(".NS", "")
    path = data_dir / f"{stem}_1D.csv"
    rows = []
    start = pd.Timestamp("2025-01-01")
    for i in range(260):
        close = base + slope * i
        rows.append(
            {
                "timestamp": (start + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
                "open": close * 0.999,
                "high": close * 1.002,
                "low": close * 0.998,
                "close": close,
                "volume": 100000 + i * 25,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def _seed_symbol_data(data_dir: Path) -> list[str]:
    symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS"]
    _write_symbol_csv(data_dir, "RELIANCE.NS", base=100.0, slope=0.40)
    _write_symbol_csv(data_dir, "TCS.NS", base=120.0, slope=0.35)
    _write_symbol_csv(data_dir, "INFY.NS", base=90.0, slope=0.28)
    return symbols


def test_run_scanner_standalone_writes_artifacts(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    symbols = _seed_symbol_data(data_dir)
    out_dir = tmp_path / "scanner_out"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner",
            "--provider",
            "csv",
            "--symbols",
            *symbols,
            "--interval",
            "day",
            "--profile",
            "morning",
            "--data-dir",
            str(data_dir),
            "--output-dir",
            str(out_dir),
            "--no-timestamped-output",
        ],
    )
    exit_code = run_scanner.main()
    assert exit_code == 0
    assert (out_dir / "scanner_candidates.csv").exists()
    assert (out_dir / "scanner_candidates.json").exists()
    assert (out_dir / "scanner_summary.md").exists()
    assert (out_dir / "scanner_artifacts_meta.json").exists()
    assert (out_dir / "run_manifest.json").exists()


def test_run_monitoring_standalone_writes_artifacts(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    symbols = _seed_symbol_data(data_dir)
    out_dir = tmp_path / "monitoring_out"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner",
            "--provider",
            "csv",
            "--symbols",
            *symbols,
            "--interval",
            "day",
            "--profile",
            "intraday",
            "--data-dir",
            str(data_dir),
            "--output-dir",
            str(out_dir),
            "--no-timestamped-output",
        ],
    )
    exit_code = run_monitoring.main()
    assert exit_code == 0
    assert (out_dir / "monitored_setups.csv").exists()
    assert (out_dir / "monitored_setups.json").exists()
    assert (out_dir / "monitoring_decision_input.json").exists()
    assert (out_dir / "monitoring_summary.md").exists()
    assert (out_dir / "monitoring_artifacts_meta.json").exists()
    assert (out_dir / "run_manifest.json").exists()


def test_run_decision_standalone_writes_artifacts(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    symbols = _seed_symbol_data(data_dir)
    out_dir = tmp_path / "decision_out"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner",
            "--provider",
            "csv",
            "--symbols",
            *symbols,
            "--interval",
            "day",
            "--profile",
            "eod",
            "--data-dir",
            str(data_dir),
            "--output-dir",
            str(out_dir),
            "--no-timestamped-output",
            "--paper-handoff",
        ],
    )
    exit_code = run_decision.main()
    assert exit_code == 0
    assert (out_dir / "decision_candidates.csv").exists()
    assert (out_dir / "decision_selected.json").exists()
    assert (out_dir / "decision_rejected.json").exists()
    assert (out_dir / "decision_summary.md").exists()
    assert (out_dir / "decision_artifacts_meta.json").exists()
    assert (out_dir / "portfolio_plan.json").exists()
    assert (out_dir / "portfolio_plan.csv").exists()
    assert (out_dir / "portfolio_risk_summary.json").exists()
    assert (out_dir / "allocation_summary.md").exists()
    assert (out_dir / "portfolio_artifacts_meta.json").exists()
    assert (out_dir / "run_manifest.json").exists()
    assert (out_dir / "paper_handoff_candidates.csv").exists()


def test_scanner_to_monitoring_to_decision_chain(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    symbols = _seed_symbol_data(data_dir)

    scanner_out = tmp_path / "scanner_chain"
    monitoring_out = tmp_path / "monitoring_chain"
    decision_out = tmp_path / "decision_chain"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner",
            "--provider",
            "csv",
            "--symbols",
            *symbols,
            "--interval",
            "day",
            "--profile",
            "morning",
            "--data-dir",
            str(data_dir),
            "--output-dir",
            str(scanner_out),
            "--no-timestamped-output",
        ],
    )
    assert run_scanner.main() == 0

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner",
            "--provider",
            "csv",
            "--interval",
            "day",
            "--profile",
            "intraday",
            "--data-dir",
            str(data_dir),
            "--scanner-input-dir",
            str(scanner_out),
            "--output-dir",
            str(monitoring_out),
            "--no-timestamped-output",
        ],
    )
    assert run_monitoring.main() == 0
    assert (monitoring_out / "monitoring_decision_input.json").exists()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner",
            "--provider",
            "csv",
            "--interval",
            "day",
            "--profile",
            "eod",
            "--data-dir",
            str(data_dir),
            "--monitoring-input-dir",
            str(monitoring_out),
            "--output-dir",
            str(decision_out),
            "--no-timestamped-output",
        ],
    )
    assert run_decision.main() == 0
    assert (decision_out / "decision_selected.json").exists()
    assert (decision_out / "portfolio_plan.json").exists()
    assert (decision_out / "run_manifest.json").exists()

    decision_manifest = json.loads((decision_out / "run_manifest.json").read_text(encoding="utf-8"))
    assert decision_manifest["contract_id"] == "decision_runner_v1"
    assert "portfolio_plan_json" in decision_manifest["expected_artifacts"]


def test_monitoring_chain_fails_clearly_when_scanner_artifacts_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_monitoring._resolve_symbols_from_scanner_artifacts(tmp_path / "missing_scanner")  # type: ignore[attr-defined]


def test_decision_chain_fails_clearly_when_monitoring_artifacts_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_decision._monitoring_result_from_artifacts(tmp_path / "missing_monitoring")  # type: ignore[attr-defined]
