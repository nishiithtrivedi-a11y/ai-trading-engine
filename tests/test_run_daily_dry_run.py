from __future__ import annotations

import sys
from pathlib import Path

from scripts import run_daily_dry_run
from src.runtime.daily_dry_run import DailyDryRunResult, DailyDryRunStageResult


def _fake_result(output_dir: Path, success: bool = True) -> DailyDryRunResult:
    stage = DailyDryRunStageResult(
        stage_name="scanner",
        success=success,
        output_dir=str(output_dir / "scanner"),
        contract_id="scanner_bundle_v1",
        manifest_path=str(output_dir / "scanner" / "run_manifest.json"),
        validation={"is_valid": success},
    )
    return DailyDryRunResult(
        success=success,
        generated_at="2026-03-17T00:00:00+00:00",
        output_dir=str(output_dir),
        provider_name="csv",
        symbols=["RELIANCE.NS", "TCS.NS", "INFY.NS"],
        timeframe="1D",
        stages=[stage],
        exports={
            "daily_dry_run_summary_json": str(output_dir / "daily_dry_run_summary.json"),
            "daily_dry_run_summary_md": str(output_dir / "daily_dry_run_summary.md"),
        },
    )


def test_run_daily_dry_run_script_returns_success(tmp_path: Path, monkeypatch) -> None:
    def _fake_run(self):  # noqa: ANN001
        return _fake_result(tmp_path, success=True)

    monkeypatch.setattr(run_daily_dry_run.DailyDryRunOrchestrator, "run", _fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        ["runner", "--output-dir", str(tmp_path), "--symbols-limit", "3"],
    )
    exit_code = run_daily_dry_run.main()
    assert exit_code == 0


def test_run_daily_dry_run_script_returns_failure(tmp_path: Path, monkeypatch) -> None:
    def _fake_run(self):  # noqa: ANN001
        return _fake_result(tmp_path, success=False)

    monkeypatch.setattr(run_daily_dry_run.DailyDryRunOrchestrator, "run", _fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        ["runner", "--output-dir", str(tmp_path), "--symbols-limit", "3"],
    )
    exit_code = run_daily_dry_run.main()
    assert exit_code == 1
