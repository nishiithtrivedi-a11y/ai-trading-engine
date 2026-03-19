"""
API route for unified platform status.

Exposes platform status combining provider sessions, runtime data
source, market session state, and feature availability in one call.

SAFETY: Read-only — no execution paths.
"""

from __future__ import annotations

from fastapi import APIRouter
from typing import Any

from src.api.services.platform_status_service import get_platform_status
from src.providers.session_manager import ProviderSessionManager

router = APIRouter(prefix="/api/v1/platform", tags=["platform"])

# Reuse the same session manager instance as provider_sessions router
from src.api.routers.provider_sessions import _session_manager


@router.get("/status")
def platform_status() -> dict[str, Any]:
    """Unified platform status snapshot.

    Returns provider session state, active runtime data source,
    market session phase, and feature availability mode.

    SAFETY: Read-only. No execution paths. No secrets exposed.
    """
    status = get_platform_status(session_manager=_session_manager)
    return status.to_dict()
