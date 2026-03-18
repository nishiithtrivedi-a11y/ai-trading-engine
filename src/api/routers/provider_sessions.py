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

class CredentialsDictionaryInput(BaseModel):
    credentials: dict[str, str] = Field(..., description="Dictionary of credential names to values")


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


@router.post("/{provider_type}/credentials")
def configure_multiple_credentials(provider_type: str, body: CredentialsDictionaryInput) -> dict[str, Any]:
    """Atomically store multiple credentials and return updated provider state."""
    try:
        pt = ProviderType(provider_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider_type}")
        
    for k, v in body.credentials.items():
        _session_manager.configure_credential(pt, k, v)
        
    # Revalidate and return new state
    state = _session_manager.validate_session(pt)
    return {"provider": state.to_dict()}


# ---------------------------------------------------------------------------
# OAuth / Browser Callback Routes
# ---------------------------------------------------------------------------
from fastapi.responses import HTMLResponse

def _callback_html(provider_name: str, success: bool, error_msg: str = "") -> HTMLResponse:
    if success:
        html = f"""
        <html><body>
            <h2>{provider_name} Connected Successfully!</h2>
            <p>You can close this window now.</p>
            <script>
                setTimeout(function() {{ window.close(); }}, 2000);
            </script>
        </body></html>
        """
    else:
        html = f"""
        <html><body>
            <h2 style="color:red;">{provider_name} Connection Failed</h2>
            <p>{error_msg}</p>
        </body></html>
        """
    return HTMLResponse(content=html)

@router.get("/zerodha/login")
def zerodha_login() -> dict[str, Any]:
    """Get the Zerodha kite login URL."""
    from src.utils.kite_auth import get_login_url
    try:
        url = get_login_url()
        return {"login_url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/zerodha/callback")
def zerodha_callback(action: str = "", request_token: str = "") -> HTMLResponse:
    """Zerodha OAuth Callback Handler."""
    if not request_token:
        return _callback_html("Zerodha", False, "Missing request_token in callback")
    
    try:
        from src.utils.kite_auth import generate_access_token
        access_token = generate_access_token(request_token)
        _session_manager.configure_credential(ProviderType.ZERODHA, "ACCESS_TOKEN", access_token)
        _session_manager.validate_session(ProviderType.ZERODHA)
        return _callback_html("Zerodha", True)
    except Exception as e:
        return _callback_html("Zerodha", False, str(e))


@router.get("/upstox/login")
def upstox_login() -> dict[str, Any]:
    """Get the Upstox login URL."""
    from src.utils.upstox_auth import get_login_url
    try:
        url = get_login_url()
        return {"login_url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/upstox/callback")
def upstox_callback(code: str = "") -> HTMLResponse:
    """Upstox OAuth Callback Handler."""
    if not code:
        return _callback_html("Upstox", False, "Missing code in callback")
    
    try:
        from src.utils.upstox_auth import generate_access_token
        access_token = generate_access_token(code)
        _session_manager.configure_credential(ProviderType.UPSTOX, "ACCESS_TOKEN", access_token)
        _session_manager.validate_session(ProviderType.UPSTOX)
        return _callback_html("Upstox", True)
    except Exception as e:
        return _callback_html("Upstox", False, str(e))
