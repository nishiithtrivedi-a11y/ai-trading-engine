"""
Provider session manager.

Manages session lifecycle for all configured providers. Validates
connections without placing orders. Connecting a provider does NOT
enable live trading — execution remains structurally disabled.
"""

from __future__ import annotations

import logging
import os
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
            return self.get_status(provider_type)

        creds = {}
        for cred_name in config.required_credentials:
            env_key = f"{config.env_key_prefix}_{cred_name}"
            creds[cred_name] = os.environ.get(env_key, "")
            
        masked_indicators = self.credential_store.get_masked_indicators(provider_type)
        now = datetime.now(timezone.utc).isoformat()

        session_status = SessionStatus.ERROR.value
        diagnostics_summary = ""
        error_message = None

        try:
            if provider_type == ProviderType.ZERODHA:
                from kiteconnect import KiteConnect
                kite = KiteConnect(api_key=creds.get("API_KEY", ""))
                access_token = creds.get("ACCESS_TOKEN")
                if access_token:
                    kite.set_access_token(access_token)
                    profile = kite.profile()
                    user_name = profile.get("user_name", "Unknown") if isinstance(profile, dict) else "Unknown"
                    diagnostics_summary = f"Zerodha session validated. User: {user_name}"
                    session_status = SessionStatus.ACTIVE.value
                else:
                    diagnostics_summary = "Zerodha API Key present, but Access Token missing."
                    session_status = SessionStatus.CREDENTIALS_MISSING.value

            elif provider_type == ProviderType.DHAN:
                from dhanhq import dhanhq
                client_id = creds.get("CLIENT_ID")
                access_token = creds.get("ACCESS_TOKEN")
                if client_id and access_token:
                    dhan = dhanhq(client_id, access_token)
                    funds = dhan.get_fund_limits()
                    if funds and isinstance(funds, dict):
                        diagnostics_summary = "DhanHQ session validated successfully."
                        session_status = SessionStatus.ACTIVE.value
                    else:
                        raise ValueError("Invalid response from DhanHQ get_fund_limits()")
                else:
                    diagnostics_summary = "DhanHQ credentials incomplete."
                    session_status = SessionStatus.CREDENTIALS_MISSING.value

            elif provider_type == ProviderType.UPSTOX:
                import upstox_client
                configuration = upstox_client.Configuration()
                configuration.access_token = creds.get("ACCESS_TOKEN", "")
                
                # Upstox client requires proper instantiation to test the token
                api_client = upstox_client.ApiClient(configuration)
                api_instance = upstox_client.UserApi(api_client)
                profile_response = api_instance.get_profile()
                
                # Depending on version, response might be an object
                if hasattr(profile_response, "data") and hasattr(profile_response.data, "user_name"):
                    user_name = profile_response.data.user_name
                else:
                    user_name = "Validated"
                    
                diagnostics_summary = f"Upstox session validated. User: {user_name}"
                session_status = SessionStatus.ACTIVE.value
            else:
                diagnostics_summary = f"Validation not implemented for {provider_type.value}."
                session_status = SessionStatus.ACTIVE.value

        except ImportError as e:
            session_status = SessionStatus.INVALID.value
            error_message = f"SDK not installed: {e}"
            diagnostics_summary = "Required provider SDK is not installed in this environment."
            logger.warning("Provider validation missing SDK: %s", e)
        except Exception as e:
            session_status = SessionStatus.INVALID.value
            error_message = str(e)
            diagnostics_summary = f"Session validation failed: {type(e).__name__}"
            logger.warning("Provider validation failed: %s", e)

        state = ProviderSessionState(
            provider_type=provider_type.value,
            display_name=config.display_name,
            session_status=session_status,
            credentials_present=True,
            last_validated=now,
            masked_indicators=masked_indicators,
            diagnostics_summary=diagnostics_summary,
            error_message=error_message,
        )

        self._session_cache[provider_type.value] = state
        logger.info(
            "Provider %s session validated at %s (Status: %s)",
            provider_type.value,
            now,
            session_status,
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
