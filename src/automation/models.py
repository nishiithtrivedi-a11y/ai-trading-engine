"""
Domain models for the Phase 21 automation / scheduling layer.

All models are serializer-friendly and compatible with JSON persistence.
No execution paths are opened by these models.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PipelineType(str, Enum):
    """Bounded set of safe pipeline types that automation can trigger."""
    MORNING_SCAN = "morning_scan"
    INTRADAY_REFRESH = "intraday_refresh"
    DECISION_REFRESH = "decision_refresh"
    EOD_PROCESSING = "eod_processing"
    PAPER_REFRESH = "paper_refresh"
    LIVE_SAFE_REFRESH = "live_safe_refresh"
    MANUAL_RESCAN = "manual_rescan"


class TriggerSource(str, Enum):
    """How a run was initiated."""
    SCHEDULED = "scheduled"
    MANUAL_UI = "manual_ui"
    MANUAL_API = "manual_api"


class RunStatus(str, Enum):
    """Lifecycle status for a single run."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Pipeline → RunMode / WorkflowType mapping
# ---------------------------------------------------------------------------

_PIPELINE_EXECUTION_MODES: dict[PipelineType, str] = {
    PipelineType.MORNING_SCAN: "research",
    PipelineType.INTRADAY_REFRESH: "research",
    PipelineType.DECISION_REFRESH: "research",
    PipelineType.EOD_PROCESSING: "research",
    PipelineType.PAPER_REFRESH: "paper",
    PipelineType.LIVE_SAFE_REFRESH: "live_safe",
    PipelineType.MANUAL_RESCAN: "research",
}


def execution_mode_for_pipeline(pipeline: PipelineType) -> str:
    """Return the execution_mode metadata string for a pipeline type.

    This NEVER returns 'live'. All automation runs remain non-executing.
    """
    return _PIPELINE_EXECUTION_MODES[pipeline]


# ---------------------------------------------------------------------------
# Job definition
# ---------------------------------------------------------------------------

@dataclass
class JobDefinition:
    """Persistent definition linking a pipeline type to a schedule."""
    job_id: str
    pipeline_type: PipelineType
    name: str
    description: str = ""
    enabled: bool = False
    schedule_mode: str = "manual"  # manual | interval | daily
    schedule_interval_minutes: Optional[int] = None
    schedule_daily_time: Optional[str] = None
    schedule_timezone: str = "Asia/Kolkata"
    cooldown_seconds: int = 300  # minimum gap between runs
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "pipeline_type": self.pipeline_type.value,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "schedule_mode": self.schedule_mode,
            "schedule_interval_minutes": self.schedule_interval_minutes,
            "schedule_daily_time": self.schedule_daily_time,
            "schedule_timezone": self.schedule_timezone,
            "cooldown_seconds": self.cooldown_seconds,
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# Run record
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunRecord:
    """Immutable record of a single pipeline run."""
    run_id: str = field(default_factory=lambda: uuid4().hex[:12])
    job_id: str = ""
    pipeline_type: str = ""
    trigger_source: str = TriggerSource.MANUAL_UI.value
    status: str = RunStatus.QUEUED.value
    execution_mode: str = "research"
    started_at: str = field(default_factory=_utc_now)
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    linked_artifacts: list[str] = field(default_factory=list)
    manifest_path: Optional[str] = None
    error_message: Optional[str] = None
    error_details: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "job_id": self.job_id,
            "pipeline_type": self.pipeline_type,
            "trigger_source": self.trigger_source,
            "status": self.status,
            "execution_mode": self.execution_mode,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "linked_artifacts": list(self.linked_artifacts),
            "manifest_path": self.manifest_path,
            "error_message": self.error_message,
            "error_details": self.error_details,
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------

@dataclass
class RunManifest:
    """Structured manifest emitted for every automation run."""
    schema_version: str = "1.0"
    run_id: str = ""
    job_id: str = ""
    pipeline_type: str = ""
    trigger_source: str = ""
    execution_mode: str = "research"
    status: str = ""
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0
    profile: str = ""
    provider: str = ""
    linked_artifacts: list[str] = field(default_factory=list)
    failure_details: Optional[str] = None
    safety_notes: list[str] = field(
        default_factory=lambda: ["Execution remains disabled. No broker orders placed."]
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "job_id": self.job_id,
            "pipeline_type": self.pipeline_type,
            "trigger_source": self.trigger_source,
            "execution_mode": self.execution_mode,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "profile": self.profile,
            "provider": self.provider,
            "linked_artifacts": list(self.linked_artifacts),
            "failure_details": self.failure_details,
            "safety_notes": list(self.safety_notes),
            "metadata": dict(self.metadata),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=True)


# ---------------------------------------------------------------------------
# Default job definitions (factory)
# ---------------------------------------------------------------------------

def default_job_definitions() -> list[JobDefinition]:
    """Return the built-in set of safe automation job definitions."""
    return [
        JobDefinition(
            job_id="morning_scan",
            pipeline_type=PipelineType.MORNING_SCAN,
            name="Morning Market Scan",
            description="Broad morning opportunity discovery for session planning.",
            enabled=False,
            schedule_mode="daily",
            schedule_daily_time="09:15",
        ),
        JobDefinition(
            job_id="intraday_refresh",
            pipeline_type=PipelineType.INTRADAY_REFRESH,
            name="Intraday Monitoring Refresh",
            description="Focused intraday refresh with tighter symbol scope.",
            enabled=False,
            schedule_mode="interval",
            schedule_interval_minutes=30,
        ),
        JobDefinition(
            job_id="decision_refresh",
            pipeline_type=PipelineType.DECISION_REFRESH,
            name="Decision Artifact Refresh",
            description="Refresh decision engine outputs and picks.",
            enabled=False,
            schedule_mode="manual",
        ),
        JobDefinition(
            job_id="eod_processing",
            pipeline_type=PipelineType.EOD_PROCESSING,
            name="End of Day Processing",
            description="End-of-day consolidation and next-session planning.",
            enabled=False,
            schedule_mode="daily",
            schedule_daily_time="15:45",
        ),
        JobDefinition(
            job_id="paper_refresh",
            pipeline_type=PipelineType.PAPER_REFRESH,
            name="Paper Trading Refresh",
            description="Refresh paper-trading artifact state.",
            enabled=False,
            schedule_mode="manual",
        ),
        JobDefinition(
            job_id="live_safe_refresh",
            pipeline_type=PipelineType.LIVE_SAFE_REFRESH,
            name="Live-Safe Signal Refresh",
            description="Refresh live-safe signal generation (no execution).",
            enabled=False,
            schedule_mode="manual",
        ),
    ]
