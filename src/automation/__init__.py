"""
Phase 21 — Automation, scheduling, and notification framework.

Provides safe, bounded, repeatable pipeline execution with run history
and outbound notification support. Execution remains structurally disabled.
"""

from src.automation.models import (
    JobDefinition,
    PipelineType,
    RunManifest,
    RunRecord,
    RunStatus,
    TriggerSource,
)

__all__ = [
    "JobDefinition",
    "PipelineType",
    "RunManifest",
    "RunRecord",
    "RunStatus",
    "TriggerSource",
]
