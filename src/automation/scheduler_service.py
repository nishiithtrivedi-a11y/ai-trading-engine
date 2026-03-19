"""
Automation scheduler service — dispatcher and orchestrator.

Manages job definitions, computes next run times by delegating to the
existing monitoring Scheduler, and dispatches safe pipeline runs through
the existing WorkflowOrchestrator. Rate-limits to prevent duplicate runs.

SAFETY: All dispatched runs set execution_mode to research/paper/live_safe.
No live execution path is reachable from this service.
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

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
from src.automation.run_store import RunStore
from src.monitoring.models import ScheduleMode, ScheduleSpec
from src.monitoring.scheduler import Scheduler
from src.runtime.workflow_orchestrator import WorkflowOrchestrator


class AutomationServiceError(RuntimeError):
    """Raised when automation dispatch fails."""


class CooldownViolationError(AutomationServiceError):
    """Raised when a run is attempted within the cooldown window."""


# ---------------------------------------------------------------------------
# Pipeline dispatcher callback type
# ---------------------------------------------------------------------------

PipelineRunner = Callable[[PipelineType, str], dict[str, Any]]
"""Signature: (pipeline_type, output_dir) -> result dict with keys like
   success (bool), artifacts (list[str]), errors (list[str])."""


def _noop_runner(pipeline_type: PipelineType, output_dir: str) -> dict[str, Any]:
    """Default no-op runner for when no real runner is wired."""
    return {
        "success": True,
        "artifacts": [],
        "errors": [],
        "message": f"No-op run for {getattr(pipeline_type, 'value', pipeline_type)}",
    }


def _orchestrator_runner(pipeline_type: PipelineType, output_dir: str) -> dict[str, Any]:
    """Real runner using the system WorkflowOrchestrator."""
    orchestrator = WorkflowOrchestrator()
    result = orchestrator.run(
        workflow=pipeline_type,
        output_root=output_dir,
        symbols_limit=0,  # Limits are configured by pipelines inherently
    )

    artifacts = []
    return {
        "success": result.success,
        "artifacts": artifacts, # Artifacts can be gathered if needed
        "errors": result.errors,
        "message": f"Orchestrated run for {getattr(pipeline_type, 'value', pipeline_type)}",
    }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

@dataclass
class AutomationSchedulerService:
    """Central automation service managing jobs, scheduling, and dispatch."""

    run_store: RunStore = field(default_factory=RunStore)
    jobs: list[JobDefinition] = field(default_factory=default_job_definitions)
    output_root: Path = field(default_factory=lambda: Path("output/automation"))
    runner: PipelineRunner = field(default=_orchestrator_runner)

    # Notification hook: called with (notification_type, title, message, metadata)
    notification_hook: Optional[Callable[..., None]] = None

    # Internal cooldown tracking
    _last_run_times: dict[str, float] = field(default_factory=dict)

    def get_job(self, job_id: str) -> Optional[JobDefinition]:
        """Look up a job definition by ID."""
        for job in self.jobs:
            if job.job_id == job_id:
                return job
        return None

    def get_all_schedules(self) -> list[dict[str, Any]]:
        """Return all job definitions with next/last run info."""
        results: list[dict[str, Any]] = []
        for job in self.jobs:
            schedule_info = job.to_dict()

            # Compute next run using existing Scheduler
            next_run = self._compute_next_run(job)
            schedule_info["next_run"] = next_run

            # Get last run from store
            last_runs = self.run_store.get_runs_by_job(job.job_id, limit=1)
            if last_runs:
                last = last_runs[0]
                schedule_info["last_run"] = {
                    "run_id": last.run_id,
                    "status": last.status,
                    "started_at": last.started_at,
                    "completed_at": last.completed_at,
                    "duration_seconds": last.duration_seconds,
                }
            else:
                schedule_info["last_run"] = None

            results.append(schedule_info)
        return results

    def trigger_pipeline(
        self,
        pipeline_type: PipelineType | str,
        trigger_source: TriggerSource | str = TriggerSource.MANUAL_UI,
    ) -> RunRecord:
        """Dispatch a pipeline run with safety and rate-limit checks."""
        if isinstance(pipeline_type, str):
            pipeline_type = PipelineType(pipeline_type)
        if isinstance(trigger_source, str):
            trigger_source = TriggerSource(trigger_source)

        # Find matching job for cooldown enforcement
        job = self._find_job_for_pipeline(pipeline_type)
        job_id = job.job_id if job else pipeline_type.value

        # Cooldown check
        self._enforce_cooldown(job_id, job.cooldown_seconds if job else 300)

        # Create run record
        execution_mode = execution_mode_for_pipeline(pipeline_type)

        record = RunRecord(
            job_id=job_id,
            pipeline_type=pipeline_type.value,
            trigger_source=trigger_source.value,
            status=RunStatus.RUNNING.value,
            execution_mode=execution_mode,
        )

        # Notify start
        self._emit_notification(
            "job_started",
            f"Pipeline Started: {pipeline_type.value}",
            f"Trigger: {trigger_source.value} | Mode: {execution_mode}",
            {"run_id": record.run_id, "pipeline_type": pipeline_type.value},
        )

        # Persist initial state
        self.run_store.save_run(record)

        # Dispatch
        start_time = _time.monotonic()
        try:
            out_dir = str(self.output_root / pipeline_type.value / record.run_id)
            result = self.runner(pipeline_type, out_dir)

            elapsed = _time.monotonic() - start_time
            record.duration_seconds = round(elapsed, 2)
            record.completed_at = datetime.now(timezone.utc).isoformat()
            record.linked_artifacts = result.get("artifacts", [])

            if result.get("success", False):
                record.status = RunStatus.COMPLETED.value
                self._emit_notification(
                    "job_completed",
                    f"Pipeline Completed: {pipeline_type.value}",
                    f"Duration: {record.duration_seconds}s | Artifacts: {len(record.linked_artifacts)}",
                    {"run_id": record.run_id, "duration": record.duration_seconds},
                )
            else:
                record.status = RunStatus.FAILED.value
                errors = result.get("errors", [])
                record.error_message = errors[0] if errors else "Unknown failure"
                record.error_details = "\n".join(errors)
                self._emit_notification(
                    "job_failed",
                    f"Pipeline Failed: {pipeline_type.value}",
                    f"Error: {record.error_message}",
                    {"run_id": record.run_id, "errors": errors},
                )

        except Exception as exc:  # noqa: BLE001
            elapsed = _time.monotonic() - start_time
            record.duration_seconds = round(elapsed, 2)
            record.completed_at = datetime.now(timezone.utc).isoformat()
            record.status = RunStatus.FAILED.value
            record.error_message = str(exc)
            record.error_details = repr(exc)
            self._emit_notification(
                "job_failed",
                f"Pipeline Failed: {pipeline_type.value}",
                f"Exception: {exc}",
                {"run_id": record.run_id},
            )

        # Write manifest
        manifest = RunManifest(
            run_id=record.run_id,
            job_id=record.job_id,
            pipeline_type=record.pipeline_type,
            trigger_source=record.trigger_source,
            execution_mode=record.execution_mode,
            status=record.status,
            started_at=record.started_at,
            completed_at=record.completed_at or "",
            duration_seconds=record.duration_seconds or 0.0,
            linked_artifacts=record.linked_artifacts,
            failure_details=record.error_details,
        )
        manifest_dir = Path(self.output_root / pipeline_type.value / record.run_id)
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / "run_manifest.json"
        manifest_path.write_text(manifest.to_json(), encoding="utf-8")
        record.manifest_path = str(manifest_path)

        # Persist final state
        self._last_run_times[job_id] = _time.monotonic()
        self.run_store.save_run(record)
        return record

    def _find_job_for_pipeline(self, pipeline_type: PipelineType) -> Optional[JobDefinition]:
        for job in self.jobs:
            if job.pipeline_type == pipeline_type:
                return job
        return None

    def _enforce_cooldown(self, job_id: str, cooldown_seconds: int) -> None:
        last = self._last_run_times.get(job_id)
        if last is not None:
            elapsed = _time.monotonic() - last
            if elapsed < cooldown_seconds:
                remaining = int(cooldown_seconds - elapsed)
                raise CooldownViolationError(
                    f"Job '{job_id}' is within cooldown window. "
                    f"Try again in {remaining}s."
                )

    def _compute_next_run(self, job: JobDefinition) -> Optional[str]:
        if not job.enabled or job.schedule_mode == "manual":
            return None
        try:
            spec = ScheduleSpec(
                name=job.job_id,
                mode=ScheduleMode(job.schedule_mode),
                enabled=job.enabled,
                interval_minutes=job.schedule_interval_minutes,
                daily_time=job.schedule_daily_time,
                timezone=job.schedule_timezone,
            )
            scheduler = Scheduler(schedule=spec)
            next_time = scheduler.next_run_time()
            return next_time.isoformat() if next_time is not None else None
        except Exception:  # noqa: BLE001
            return None

    def _emit_notification(
        self,
        notification_type: str,
        title: str,
        message: str,
        metadata: dict[str, Any],
    ) -> None:
        if self.notification_hook is not None:
            try:
                self.notification_hook(notification_type, title, message, metadata)
            except Exception:  # noqa: BLE001
                pass  # notification failures must not break automation
