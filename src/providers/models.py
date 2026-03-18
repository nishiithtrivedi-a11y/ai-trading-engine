"""
Provider session and credential domain models.

These models describe provider connection status, session state,
and credential presence without ever holding raw secrets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class ProviderType(str, Enum):
    """Supported provider types."""
    ZERODHA = "zerodha"
    DHAN = "dhan"
    UPSTOX = "upstox"


class SessionStatus(str, Enum):
    """Provider session lifecycle states."""
    NOT_CONFIGURED = "not_configured"
    CREDENTIALS_MISSING = "credentials_missing"
    ACTIVE = "active"
    EXPIRED = "expired"
    INVALID = "invalid"
    ERROR = "error"


class AuthType(str, Enum):
    """Authentication type used by the provider."""
    API_KEY = "api_key"
    OAUTH = "oauth"
    TOKEN = "token"


@dataclass
class ProviderConfig:
    """Static configuration for a provider."""
    provider_type: ProviderType
    display_name: str
    requires_session: bool = True
    auth_type: AuthType = AuthType.API_KEY
    env_key_prefix: str = ""
    required_credentials: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_type": self.provider_type.value,
            "display_name": self.display_name,
            "requires_session": self.requires_session,
            "auth_type": self.auth_type.value,
            "description": self.description,
        }


@dataclass
class ProviderSessionState:
    """Current session state for a provider — never holds raw secrets."""
    provider_type: str
    display_name: str = ""
    session_status: str = SessionStatus.NOT_CONFIGURED.value
    credentials_present: bool = False
    last_validated: Optional[str] = None
    expiry_time: Optional[str] = None
    error_message: Optional[str] = None
    diagnostics_summary: str = ""
    masked_indicators: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_type": self.provider_type,
            "display_name": self.display_name,
            "session_status": self.session_status,
            "credentials_present": self.credentials_present,
            "last_validated": self.last_validated,
            "expiry_time": self.expiry_time,
            "error_message": self.error_message,
            "diagnostics_summary": self.diagnostics_summary,
            "masked_indicators": dict(self.masked_indicators),
        }


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

PROVIDER_REGISTRY: dict[ProviderType, ProviderConfig] = {
    ProviderType.ZERODHA: ProviderConfig(
        provider_type=ProviderType.ZERODHA,
        display_name="Zerodha Kite",
        requires_session=True,
        auth_type=AuthType.TOKEN,
        env_key_prefix="ZERODHA",
        required_credentials=("API_KEY", "API_SECRET", "ACCESS_TOKEN"),
        description="Zerodha Kite Connect session-based access.",
    ),
    ProviderType.DHAN: ProviderConfig(
        provider_type=ProviderType.DHAN,
        display_name="DhanHQ",
        requires_session=True,
        auth_type=AuthType.TOKEN,
        env_key_prefix="DHAN",
        required_credentials=("CLIENT_ID", "ACCESS_TOKEN"),
        description="DhanHQ token-based API access.",
    ),
    ProviderType.UPSTOX: ProviderConfig(
        provider_type=ProviderType.UPSTOX,
        display_name="Upstox",
        requires_session=True,
        auth_type=AuthType.OAUTH,
        env_key_prefix="UPSTOX",
        required_credentials=("API_KEY", "API_SECRET", "ACCESS_TOKEN"),
        description="Upstox OAuth2-based API access.",
    ),
}
