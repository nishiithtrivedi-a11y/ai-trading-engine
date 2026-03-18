"""Tests for src.automation.scheduler_service module."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.automation.models import PipelineType, RunStatus, TriggerSource
from src.automation.run_store import RunStore
from src.automation.scheduler_service import (
    AutomationSchedulerService,
    CooldownViolationError,
)


def _make_service(tmp_path: Path) -> AutomationSchedulerService:
    store = RunStore(store_dir=tmp_path / "runs")
    return AutomationSchedulerService(
        run_store=store,
        output_root=tmp_path / "output",
    )


def test_trigger_pipeline_creates_run(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    record = svc.trigger_pipeline(PipelineType.MORNING_SCAN, TriggerSource.MANUAL_UI)
    assert record.status == RunStatus.COMPLETED.value
    assert record.execution_mode == "research"
    assert record.pipeline_type == "morning_scan"
    assert record.trigger_source == "manual_ui"


def test_trigger_writes_manifest(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    record = svc.trigger_pipeline(PipelineType.MORNING_SCAN)
    assert record.manifest_path is not None
    manifest_path = Path(record.manifest_path)
    assert manifest_path.exists()


def test_trigger_records_in_store(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    record = svc.trigger_pipeline(PipelineType.MORNING_SCAN)
    loaded = svc.run_store.get_run(record.run_id)
    assert loaded is not None
    assert loaded.run_id == record.run_id


def test_cooldown_enforcement(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    svc.trigger_pipeline(PipelineType.MORNING_SCAN)
    with pytest.raises(CooldownViolationError):
        svc.trigger_pipeline(PipelineType.MORNING_SCAN)


def test_paper_pipeline_uses_paper_mode(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    record = svc.trigger_pipeline(PipelineType.PAPER_REFRESH)
    assert record.execution_mode == "paper"


def test_live_safe_pipeline_uses_live_safe_mode(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    record = svc.trigger_pipeline(PipelineType.LIVE_SAFE_REFRESH)
    assert record.execution_mode == "live_safe"


def test_execution_mode_never_live(tmp_path: Path) -> None:
    """SAFETY: no pipeline should ever produce a live execution_mode."""
    svc = _make_service(tmp_path)
    # Set cooldown to 0 for this test
    for job in svc.jobs:
        job.cooldown_seconds = 0

    for pt in PipelineType:
        record = svc.trigger_pipeline(pt, TriggerSource.MANUAL_API)
        assert record.execution_mode != "live", f"{pt.value} produced live mode!"


def test_get_all_schedules(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    schedules = svc.get_all_schedules()
    assert len(schedules) >= 6
    for sch in schedules:
        assert "job_id" in sch
        assert "pipeline_type" in sch
        assert "next_run" in sch
        assert "last_run" in sch


def test_notification_hook_called(tmp_path: Path) -> None:
    called: list[str] = []
    def hook(notification_type: str, title: str, message: str, metadata: dict) -> None:
        called.append(notification_type)

    svc = _make_service(tmp_path)
    svc.notification_hook = hook
    svc.trigger_pipeline(PipelineType.MORNING_SCAN)

    assert "job_started" in called
    assert "job_completed" in called


def test_string_pipeline_type(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    record = svc.trigger_pipeline("manual_rescan", "manual_api")
    assert record.pipeline_type == "manual_rescan"
    assert record.trigger_source == "manual_api"
