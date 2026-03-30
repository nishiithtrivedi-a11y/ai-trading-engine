"""
API route for unified platform status.

Exposes platform status combining provider sessions, runtime data
source, market session state, and feature availability in one call.

SAFETY: Read-only — no execution paths.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any

from src.api.services.platform_status_service import get_platform_status
from src.providers.session_manager import ProviderSessionManager
from src.providers.models import SessionStatus
from src.data.provider_config import load_provider_config
from src.data.provider_runtime import get_provider_readiness_report

router = APIRouter(prefix="/api/v1/platform", tags=["platform"])

# Reuse the same session manager instance as provider_sessions router
from src.api.routers.provider_sessions import _session_manager

class RuntimeSourceUpdate(BaseModel):
    provider_type: str = Field(..., description="Provider to set as primary (e.g., zerodha, upstox, csv)")

@router.get("/status")
def platform_status() -> dict[str, Any]:
    """Unified platform status snapshot.

    Returns provider session state, active runtime data source,
    market session phase, and feature availability mode.

    SAFETY: Read-only. No execution paths. No secrets exposed.
    """
    status = get_platform_status(session_manager=_session_manager)
    return status.to_dict()

@router.post("/runtime-source")
def update_runtime_source(update: RuntimeSourceUpdate) -> dict[str, Any]:
    """Update the primary runtime data source.
    
    Validates that the requested provider is either 'csv' or has an active session.
    Persists the change to data_providers.yaml.
    """
    provider = update.provider_type.lower()
    
    # 1. Validation
    config = load_provider_config()

    report = get_provider_readiness_report(
        provider,
        config=config,
        session_manager=_session_manager,
        require_enabled=True,
    )
    if provider not in ("csv", "indian_csv") and not report.can_instantiate:
        raise HTTPException(
            status_code=400,
            detail=report.reason,
        )

    if provider not in ("csv", "indian_csv"):
        if str(report.session_status or "").strip().lower() != SessionStatus.ACTIVE.value:
            raise HTTPException(
                status_code=400, 
                detail=f"Provider '{provider}' does not have an active session and cannot be set as primary."
            )

    # 2. Persist to config
    try:
        config.default_provider = provider
        if not config.save_config():
            raise HTTPException(status_code=500, detail="Failed to persist configuration change.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Configuration error: {str(e)}")

    return {
        "success": True,
        "selected_provider": provider,
        "message": f"Successfully updated primary runtime source to {provider}."
    }
