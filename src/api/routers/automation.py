"""
API routes for the Phase 21 automation / scheduling layer.

Provides endpoints for schedule visibility, manual pipeline triggers,
run history, and notification preference management.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Optional

from src.automation.models import PipelineType, TriggerSource
from src.automation.run_store import RunStore
from src.automation.scheduler_service import (
    AutomationSchedulerService,
    CooldownViolationError,
)
from src.automation.notification.service import NotificationService
from src.automation.notification.models import (
    ChannelPreference,
    ContactTarget,
    NotificationPreferences,
    TypePreference,
)

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])

# ---------------------------------------------------------------------------
# Shared instances (single-process)
# ---------------------------------------------------------------------------

_run_store = RunStore()
_notification_service = NotificationService()
_scheduler_service = AutomationSchedulerService(
    run_store=_run_store,
    notification_hook=_notification_service.create_notification_hook(),
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class TriggerRequest(BaseModel):
    trigger_source: str = Field(default="manual_ui", description="manual_ui | manual_api | scheduled")


class PreferencesUpdate(BaseModel):
    channels: list[dict[str, Any]] = Field(default_factory=list)
    types: list[dict[str, Any]] = Field(default_factory=list)
    contacts: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Schedule endpoints
# ---------------------------------------------------------------------------

@router.get("/schedules")
def get_schedules() -> dict[str, Any]:
    """List all job definitions with next/last run info."""
    return {"schedules": _scheduler_service.get_all_schedules()}


# ---------------------------------------------------------------------------
# Run endpoints
# ---------------------------------------------------------------------------

@router.get("/runs")
def get_recent_runs(limit: int = 50) -> dict[str, Any]:
    """Get recent run history."""
    capped = min(max(limit, 1), 200)
    runs = _run_store.get_recent_runs(limit=capped)
    return {"runs": [r.to_dict() for r in runs]}


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    """Get details of a single run."""
    record = _run_store.get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return {"run": record.to_dict()}


# ---------------------------------------------------------------------------
# Trigger endpoints
# ---------------------------------------------------------------------------

@router.post("/trigger/{pipeline_type}")
def trigger_pipeline(pipeline_type: str, body: Optional[TriggerRequest] = None) -> dict[str, Any]:
    """Manually trigger a pipeline run (Run Pipeline / Rescan Now).

    This endpoint triggers a safe, bounded pipeline run.
    No live execution is possible — all pipelines enforce non-live execution modes.
    """
    try:
        pt = PipelineType(pipeline_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid pipeline type: {pipeline_type}. "
                   f"Valid types: {[p.value for p in PipelineType]}",
        )

    trigger_source = TriggerSource.MANUAL_UI
    if body and body.trigger_source:
        try:
            trigger_source = TriggerSource(body.trigger_source)
        except ValueError:
            trigger_source = TriggerSource.MANUAL_UI

    try:
        record = _scheduler_service.trigger_pipeline(pt, trigger_source)
        return {"run": record.to_dict()}
    except CooldownViolationError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline dispatch failed: {exc}")


# ---------------------------------------------------------------------------
# Notification preferences endpoints
# ---------------------------------------------------------------------------

@router.get("/notification/preferences")
def get_notification_preferences() -> dict[str, Any]:
    """Get current notification preferences (contact values are masked)."""
    prefs = _notification_service.get_preferences()
    return {"preferences": prefs.to_safe_dict()}


@router.put("/notification/preferences")
def update_notification_preferences(body: PreferencesUpdate) -> dict[str, Any]:
    """Update notification preferences."""
    try:
        channels = [ChannelPreference(**ch) for ch in body.channels]
        types = [TypePreference(**tp) for tp in body.types]
        contacts = [ContactTarget(**ct) for ct in body.contacts]
        prefs = NotificationPreferences(
            channels=channels, types=types, contacts=contacts,
        )
        _notification_service.save_preferences(prefs)
        return {"preferences": prefs.to_safe_dict(), "saved": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid preferences: {exc}")


@router.post("/notification/test/{channel_type}")
def test_notification_channel(channel_type: str) -> dict[str, Any]:
    """Send a test notification through a specific channel."""
    result = _notification_service.send_test(channel_type)
    return {"result": result.to_dict()}
