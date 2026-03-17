from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.runtime.daily_dry_run import DailyDryRunConfig, DailyDryRunOrchestrator


def _write_symbol_csv(data_dir: Path, symbol: str, closes: list[float]) -> None:
    stem = symbol.replace(".NS", "")
    path = data_dir / f"{stem}_1D.csv"
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-01", periods=len(closes), freq="D"),
            "open": closes,
            "high": [value * 1.01 for value in closes],
            "low": [value * 0.99 for value in closes],
            "close": closes,
            "volume": [1000 + i * 10 for i in range(len(closes))],
        }
    )
    df.to_csv(path, index=False)


def test_daily_dry_run_orchestrates_scanner_monitoring_decision(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS"]
    for symbol in symbols:
        _write_symbol_csv(data_dir, symbol, [100 + i * 0.3 for i in range(220)])

    config = DailyDryRunConfig(
        output_dir=str(tmp_path / "daily_dry_run"),
        provider_name="csv",
        data_dir=str(data_dir),
        symbols=symbols,
        symbols_limit=3,
        timeframe="1D",
        include_paper_handoff=True,
    )
    result = DailyDryRunOrchestrator(config=config).run()

    assert result.success is True
    assert [stage.stage_name for stage in result.stages] == ["scanner", "monitoring", "decision"]
    assert all(stage.success for stage in result.stages)

    for stage in result.stages:
        assert stage.manifest_path is not None
        assert Path(stage.manifest_path).exists()
        assert stage.validation.get("is_valid") is True

    assert "daily_dry_run_summary_json" in result.exports
    assert "daily_dry_run_summary_md" in result.exports
    assert Path(result.exports["daily_dry_run_summary_json"]).exists()
    assert Path(result.exports["daily_dry_run_summary_md"]).exists()
