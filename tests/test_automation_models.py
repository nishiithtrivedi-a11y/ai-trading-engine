"""Tests for src.automation.models module."""

from __future__ import annotations

import json

from src.automation.models import (
    JobDefinition,
    PipelineType,
    RunManifest,
    RunRecord,
    RunStatus,
    TriggerSource,
    default_job_definitions,
    execution_mode_for_pipeline,
)


def test_pipeline_type_values() -> None:
    assert PipelineType.MORNING_SCAN.value == "morning_scan"
    assert PipelineType.MANUAL_RESCAN.value == "manual_rescan"


def test_execution_mode_never_live() -> None:
    """SAFETY: no pipeline type should ever return 'live'."""
    for pt in PipelineType:
        mode = execution_mode_for_pipeline(pt)
        assert mode != "live", f"Pipeline {pt.value} returned live mode!"
        assert mode in ("research", "paper", "live_safe")


def test_job_definition_to_dict() -> None:
    job = JobDefinition(
        job_id="test",
        pipeline_type=PipelineType.MORNING_SCAN,
        name="Test Job",
    )
    d = job.to_dict()
    assert d["job_id"] == "test"
    assert d["pipeline_type"] == "morning_scan"
    assert d["enabled"] is False


def test_run_record_to_dict() -> None:
    record = RunRecord(
        run_id="abc123",
        job_id="test",
        pipeline_type="morning_scan",
        status=RunStatus.COMPLETED.value,
    )
    d = record.to_dict()
    assert d["run_id"] == "abc123"
    assert d["status"] == "completed"
    assert d["execution_mode"] == "research"


def test_run_manifest_to_json() -> None:
    manifest = RunManifest(
        run_id="abc123",
        pipeline_type="morning_scan",
        status="completed",
    )
    raw = manifest.to_json()
    parsed = json.loads(raw)
    assert parsed["run_id"] == "abc123"
    assert "Execution remains disabled" in parsed["safety_notes"][0]


def test_default_job_definitions() -> None:
    jobs = default_job_definitions()
    assert len(jobs) >= 6
    job_ids = {j.job_id for j in jobs}
    assert "morning_scan" in job_ids
    assert "eod_processing" in job_ids
    # All jobs start disabled
    for j in jobs:
        assert j.enabled is False
