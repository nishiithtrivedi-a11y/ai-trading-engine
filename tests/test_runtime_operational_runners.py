from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.runtime.operational_runners import (
    RunnerArtifactResolutionError,
    get_runner_schedule_profile,
    resolve_latest_runner_dir,
    resolve_runner_output_dir,
    write_runner_artifacts_meta,
)


def test_get_runner_schedule_profile_returns_expected_defaults() -> None:
    morning = get_runner_schedule_profile("morning")
    intraday = get_runner_schedule_profile("intraday")
    eod = get_runner_schedule_profile("eod")

    assert morning.default_interval == "day"
    assert intraday.default_interval == "5minute"
    assert eod.default_interval == "day"
    assert morning.default_max_symbols > intraday.default_max_symbols


def test_resolve_runner_output_dir_no_timestamp_writes_marker(tmp_path: Path) -> None:
    out_dir = resolve_runner_output_dir(
        output_dir=tmp_path / "scanner",
        runner_name="scanner",
        timestamped=False,
    )
    assert out_dir == tmp_path / "scanner"
    assert (out_dir / ".runner").exists()
    assert (out_dir / ".runner").read_text(encoding="utf-8") == "scanner"


def test_resolve_latest_runner_dir_picks_latest_manifest(tmp_path: Path) -> None:
    older = tmp_path / "20260101T000000Z"
    newer = tmp_path / "20260101T010000Z"
    older.mkdir(parents=True, exist_ok=True)
    newer.mkdir(parents=True, exist_ok=True)
    (older / "run_manifest.json").write_text("{}", encoding="utf-8")
    time.sleep(0.02)
    (newer / "run_manifest.json").write_text("{}", encoding="utf-8")

    latest = resolve_latest_runner_dir(output_dir=tmp_path)
    assert latest == newer


def test_resolve_latest_runner_dir_raises_when_missing(tmp_path: Path) -> None:
    with pytest.raises(RunnerArtifactResolutionError):
        resolve_latest_runner_dir(output_dir=tmp_path)


def test_write_runner_artifacts_meta_contains_required_fields(tmp_path: Path) -> None:
    artifact_path = tmp_path / "scanner_candidates.csv"
    artifact_path.write_text("symbol\nRELIANCE.NS\n", encoding="utf-8")

    meta_path = write_runner_artifacts_meta(
        output_path=tmp_path / "scanner_artifacts_meta.json",
        runner_name="scanner",
        profile="morning",
        provider="indian_csv",
        interval="1D",
        execution_mode="research",
        source="tests",
        artifacts={"scanner_candidates_csv": artifact_path},
        metadata={"symbols_count": 1},
    )
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "v1"
    assert payload["runner_name"] == "scanner"
    assert payload["profile"] == "morning"
    assert payload["provider"] == "indian_csv"
    assert "scanner_candidates_csv" in payload["artifacts"]
