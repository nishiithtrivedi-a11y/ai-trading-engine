"""
API routes for provider session management (Phase 21.x).

Provides endpoints for provider session status, validation,
and credential configuration. All responses mask sensitive values.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Optional

from src.providers.models import ProviderType
from src.providers.session_manager import ProviderSessionManager

router = APIRouter(prefix="/api/v1/providers/sessions", tags=["provider_sessions"])

_session_manager = ProviderSessionManager()


class CredentialInput(BaseModel):
    credential_name: str = Field(..., description="Name of the credential (e.g. API_KEY, ACCESS_TOKEN)")
    value: str = Field(..., description="Credential value — will be stored securely and masked in responses")


@router.get("")
def get_all_sessions() -> dict[str, Any]:
    """Get session status for all registered providers."""
    states = _session_manager.get_all_statuses()
    return {"providers": [s.to_dict() for s in states]}


@router.get("/{provider_type}")
def get_session(provider_type: str) -> dict[str, Any]:
    """Get session status for a single provider."""
    try:
        pt = ProviderType(provider_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider_type}")
    state = _session_manager.get_status(pt)
    return {"provider": state.to_dict()}


@router.post("/{provider_type}/validate")
def validate_session(provider_type: str) -> dict[str, Any]:
    """Validate/reconnect a provider session.

    This performs a read-only connection test. It does NOT enable
    live trading or broker order execution.
    """
    try:
        pt = ProviderType(provider_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider_type}")

    state = _session_manager.validate_session(pt)
    return {"provider": state.to_dict()}


@router.post("/{provider_type}/configure")
def configure_credential(provider_type: str, body: CredentialInput) -> dict[str, Any]:
    """Store a provider credential.

    The credential is stored securely. The response will contain
    masked indicators — never the raw value.
    """
    try:
        pt = ProviderType(provider_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider_type}")

    state = _session_manager.configure_credential(
        pt, body.credential_name, body.value,
    )
    return {"provider": state.to_dict()}
