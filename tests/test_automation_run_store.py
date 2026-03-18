"""Tests for src.automation.run_store module."""

from __future__ import annotations

import json
from pathlib import Path

from src.automation.models import RunRecord, RunStatus
from src.automation.run_store import RunStore


def test_save_and_get_run(tmp_path: Path) -> None:
    store = RunStore(store_dir=tmp_path / "runs")
    record = RunRecord(
        run_id="r001",
        job_id="morning_scan",
        pipeline_type="morning_scan",
        status=RunStatus.COMPLETED.value,
    )
    saved_path = store.save_run(record)
    assert saved_path.exists()

    loaded = store.get_run("r001")
    assert loaded is not None
    assert loaded.run_id == "r001"
    assert loaded.status == "completed"


def test_get_recent_runs(tmp_path: Path) -> None:
    store = RunStore(store_dir=tmp_path / "runs")
    for i in range(5):
        record = RunRecord(run_id=f"r{i:03d}", job_id="test", pipeline_type="morning_scan")
        store.save_run(record)

    recent = store.get_recent_runs(limit=3)
    assert len(recent) == 3


def test_get_runs_by_job(tmp_path: Path) -> None:
    store = RunStore(store_dir=tmp_path / "runs")
    store.save_run(RunRecord(run_id="a1", job_id="job_a", pipeline_type="morning_scan"))
    store.save_run(RunRecord(run_id="b1", job_id="job_b", pipeline_type="eod_processing"))
    store.save_run(RunRecord(run_id="a2", job_id="job_a", pipeline_type="morning_scan"))

    job_a_runs = store.get_runs_by_job("job_a")
    assert len(job_a_runs) == 2
    assert all(r.job_id == "job_a" for r in job_a_runs)


def test_retention_enforcement(tmp_path: Path) -> None:
    store = RunStore(store_dir=tmp_path / "runs", max_history=3)
    for i in range(5):
        store.save_run(RunRecord(run_id=f"r{i:03d}", job_id="test", pipeline_type="test"))

    files = list((tmp_path / "runs").glob("*.json"))
    assert len(files) <= 3


def test_get_nonexistent_run(tmp_path: Path) -> None:
    store = RunStore(store_dir=tmp_path / "runs")
    assert store.get_run("nonexistent") is None
