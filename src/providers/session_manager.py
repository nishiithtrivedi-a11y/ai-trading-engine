"""
Provider session manager.

Manages session lifecycle for all configured providers. Validates
connections without placing orders. Connecting a provider does NOT
enable live trading — execution remains structurally disabled.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from src.providers.credential_store import CredentialStore
from src.providers.models import (
    PROVIDER_REGISTRY,
    ProviderConfig,
    ProviderSessionState,
    ProviderType,
    SessionStatus,
)

logger = logging.getLogger("provider_session_manager")


@dataclass
class ProviderSessionManager:
    """Manages provider session lifecycle for all registered providers.

    SAFETY: Connecting a provider only validates the session / credentials.
    No live trading is enabled by any operation in this module.
    """

    credential_store: CredentialStore = field(default_factory=CredentialStore)
    _session_cache: dict[str, ProviderSessionState] = field(default_factory=dict)

    def get_all_statuses(self) -> list[ProviderSessionState]:
        """Get session state for all registered providers."""
        states: list[ProviderSessionState] = []
        for provider_type, config in PROVIDER_REGISTRY.items():
            state = self.get_status(provider_type)
            states.append(state)
        return states

    def get_status(self, provider_type: ProviderType | str) -> ProviderSessionState:
        """Get the current session state for a single provider."""
        if isinstance(provider_type, str):
            try:
                provider_type = ProviderType(provider_type)
            except ValueError:
                return ProviderSessionState(
                    provider_type=str(provider_type),
                    session_status=SessionStatus.NOT_CONFIGURED.value,
                    error_message=f"Unknown provider type: {provider_type}",
                )

        config = PROVIDER_REGISTRY.get(provider_type)
        if config is None:
            return ProviderSessionState(
                provider_type=provider_type.value,
                session_status=SessionStatus.NOT_CONFIGURED.value,
            )

        has_creds = self.credential_store.has_credentials(provider_type)
        masked = self.credential_store.get_masked_indicators(provider_type)

        if not has_creds:
            cred_status = self.credential_store.get_credential_status(provider_type)
            missing = [k for k, v in cred_status.items() if not v]
            return ProviderSessionState(
                provider_type=provider_type.value,
                display_name=config.display_name,
                session_status=SessionStatus.CREDENTIALS_MISSING.value,
                credentials_present=False,
                masked_indicators=masked,
                diagnostics_summary=f"Missing credentials: {', '.join(missing)}",
            )

        # Check cached state
        cached = self._session_cache.get(provider_type.value)
        if cached is not None:
            return cached

        # Default to configured-but-not-validated state
        return ProviderSessionState(
            provider_type=provider_type.value,
            display_name=config.display_name,
            session_status=SessionStatus.NOT_CONFIGURED.value,
            credentials_present=True,
            masked_indicators=masked,
            diagnostics_summary="Credentials present. Session not yet validated.",
        )

    def validate_session(self, provider_type: ProviderType | str) -> ProviderSessionState:
        """Validate a provider session without placing any orders.

        This performs a read-only connection test. The exact validation
        depends on the provider:
        - Zerodha: attempt profile fetch
        - DhanHQ: attempt fund margin query
        - Upstox: attempt profile fetch

        Currently uses mock validation; real broker SDK calls can be
        integrated later without changing the interface.
        """
        if isinstance(provider_type, str):
            provider_type = ProviderType(provider_type)

        config = PROVIDER_REGISTRY.get(provider_type)
        if config is None:
            return ProviderSessionState(
                provider_type=str(provider_type),
                session_status=SessionStatus.ERROR.value,
                error_message=f"Unknown provider: {provider_type}",
            )

        has_creds = self.credential_store.has_credentials(provider_type)
        if not has_creds:
            state = self.get_status(provider_type)
            return state

        # Mock validation — in future, this calls the actual broker SDK
        now = datetime.now(timezone.utc).isoformat()
        state = ProviderSessionState(
            provider_type=provider_type.value,
            display_name=config.display_name,
            session_status=SessionStatus.ACTIVE.value,
            credentials_present=True,
            last_validated=now,
            masked_indicators=self.credential_store.get_masked_indicators(provider_type),
            diagnostics_summary="Session validated successfully (mock validation).",
        )

        self._session_cache[provider_type.value] = state
        logger.info(
            "Provider %s session validated at %s",
            provider_type.value,
            now,
        )
        return state

    def configure_credential(
        self,
        provider_type: ProviderType | str,
        credential_name: str,
        value: str,
    ) -> ProviderSessionState:
        """Store a credential and return updated provider state.

        SAFETY: Storing a credential does not enable execution.
        The returned state never contains raw credential values.
        """
        if isinstance(provider_type, str):
            provider_type = ProviderType(provider_type)

        config = PROVIDER_REGISTRY.get(provider_type)
        if config is None:
            return ProviderSessionState(
                provider_type=str(provider_type),
                session_status=SessionStatus.ERROR.value,
                error_message=f"Unknown provider: {provider_type}",
            )

        if credential_name not in config.required_credentials:
            return ProviderSessionState(
                provider_type=provider_type.value,
                display_name=config.display_name,
                session_status=SessionStatus.ERROR.value,
                error_message=f"Unknown credential: {credential_name}",
            )

        stored = self.credential_store.store_credential(
            provider_type, credential_name, value,
        )
        if not stored:
            return ProviderSessionState(
                provider_type=provider_type.value,
                display_name=config.display_name,
                session_status=SessionStatus.ERROR.value,
                error_message="Failed to store credential.",
            )

        # Invalidate cache
        self._session_cache.pop(provider_type.value, None)

        # Return fresh status
        return self.get_status(provider_type)
