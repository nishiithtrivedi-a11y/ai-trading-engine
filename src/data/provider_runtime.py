"""
Shared provider runtime readiness layer.

This module centralizes provider state into one source of truth used by UI,
runners, scanners, and provider creation paths:
1) static config state (enabled/default provider),
2) credential resolution (env + compatible aliases + config fallback),
3) runtime session/auth state,
4) capability/workflow suitability checks.

No execution behavior is introduced here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from src.data.instrument_metadata import InstrumentType
from src.data.provider_capabilities import (
    ProviderCapabilityError,
    ProviderFeatureSet,
    get_provider_feature_set,
    validate_provider_workflow,
)
from src.data.provider_config import DataProvidersConfig, ProviderEntry, load_provider_config
from src.providers.models import PROVIDER_REGISTRY, SessionStatus
from src.providers.session_manager import ProviderSessionManager


class ProviderRuntimeState(str, Enum):
    DISABLED = "disabled"
    MISCONFIGURED = "misconfigured"
    MISSING_SECRETS = "missing_secrets"
    SESSION_INVALID = "session_invalid"
    READY = "ready"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class ProviderRuntimeProfile:
    provider_name: str
    display_name: str
    env_key_prefix: str
    required_credentials: tuple[str, ...]
    optional_credentials: tuple[str, ...] = ()
    requires_session: bool = False


@dataclass(frozen=True)
class ResolvedProviderCredentials:
    provider_name: str
    values: dict[str, str]
    presence: dict[str, bool]
    missing_required: tuple[str, ...]
    sources: dict[str, str]
    env_keys: dict[str, tuple[str, ...]]

    @property
    def is_fully_configured(self) -> bool:
        return not self.missing_required


@dataclass(frozen=True)
class ProviderReadinessReport:
    provider_name: str
    display_name: str
    state: ProviderRuntimeState
    reason: str
    enabled: bool
    configured: bool
    is_default_provider: bool
    requires_session: bool
    session_status: Optional[str]
    can_instantiate: bool
    credentials_required: tuple[str, ...]
    credentials_present: dict[str, bool]
    missing_credentials: tuple[str, ...]
    credential_env_keys: dict[str, tuple[str, ...]]
    capability_summary: dict[str, Any]
    workflow_supported: bool
    workflow_requirements: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "display_name": self.display_name,
            "state": self.state.value,
            "reason": self.reason,
            "enabled": self.enabled,
            "configured": self.configured,
            "is_default_provider": self.is_default_provider,
            "requires_session": self.requires_session,
            "session_status": self.session_status,
            "can_instantiate": self.can_instantiate,
            "credentials_required": list(self.credentials_required),
            "credentials_present": dict(self.credentials_present),
            "missing_credentials": list(self.missing_credentials),
            "credential_env_keys": {
                key: list(values) for key, values in self.credential_env_keys.items()
            },
            "capability_summary": dict(self.capability_summary),
            "workflow_supported": self.workflow_supported,
            "workflow_requirements": dict(self.workflow_requirements),
        }


_PROFILE_OVERRIDES: dict[str, ProviderRuntimeProfile] = {}

_STATIC_RUNTIME_PROFILES: dict[str, ProviderRuntimeProfile] = {
    "csv": ProviderRuntimeProfile(
        provider_name="csv",
        display_name="CSV",
        env_key_prefix="CSV",
        required_credentials=(),
        requires_session=False,
    ),
    "indian_csv": ProviderRuntimeProfile(
        provider_name="indian_csv",
        display_name="Indian CSV",
        env_key_prefix="INDIAN_CSV",
        required_credentials=(),
        requires_session=False,
    ),
}

_CREDENTIAL_CONFIG_FIELDS: dict[str, str] = {
    "API_KEY": "api_key",
    "API_SECRET": "api_secret",
    "ACCESS_TOKEN": "access_token",
    "CLIENT_ID": "api_key",
}

_CREDENTIAL_ENV_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "dhan": {
        "CLIENT_ID": ("DHAN_CLIENT_ID", "DHAN_API_KEY"),
        "ACCESS_TOKEN": ("DHAN_ACCESS_TOKEN",),
    },
}


def _normalize_provider_name(provider_name: str) -> str:
    name = str(provider_name).strip().lower()
    if not name:
        raise ValueError("provider_name cannot be empty")
    return name


def register_provider_runtime_profile(profile: ProviderRuntimeProfile) -> None:
    _PROFILE_OVERRIDES[_normalize_provider_name(profile.provider_name)] = profile


def _build_default_profiles() -> dict[str, ProviderRuntimeProfile]:
    profiles = dict(_STATIC_RUNTIME_PROFILES)
    for provider_type, provider_cfg in PROVIDER_REGISTRY.items():
        key = provider_type.value
        required_credentials = tuple(provider_cfg.required_credentials)
        optional_credentials: tuple[str, ...] = ()
        # Upstox supports degraded CSV fallback by design; credentials are
        # optional for instantiation even though session validation needs them.
        if key == "upstox":
            optional_credentials = required_credentials
            required_credentials = ()
        profiles[key] = ProviderRuntimeProfile(
            provider_name=key,
            display_name=provider_cfg.display_name,
            env_key_prefix=str(provider_cfg.env_key_prefix or key).strip().upper(),
            required_credentials=required_credentials,
            optional_credentials=optional_credentials,
            requires_session=bool(provider_cfg.requires_session),
        )
    return profiles


def get_provider_runtime_profile(provider_name: str) -> Optional[ProviderRuntimeProfile]:
    name = _normalize_provider_name(provider_name)
    if name in _PROFILE_OVERRIDES:
        return _PROFILE_OVERRIDES[name]
    return _build_default_profiles().get(name)


def _env_candidates(profile: ProviderRuntimeProfile, credential_name: str) -> tuple[str, ...]:
    name = str(credential_name).strip().upper()
    defaults = (f"{profile.env_key_prefix}_{name}",)
    aliases = _CREDENTIAL_ENV_ALIASES.get(profile.provider_name, {}).get(name, ())
    merged: list[str] = []
    for candidate in defaults + aliases:
        if candidate and candidate not in merged:
            merged.append(candidate)
    return tuple(merged)


def _resolve_config_credential(
    entry: Optional[ProviderEntry],
    credential_name: str,
) -> str:
    if entry is None:
        return ""
    field_name = _CREDENTIAL_CONFIG_FIELDS.get(str(credential_name).strip().upper())
    if not field_name:
        return ""
    raw = getattr(entry, field_name, "")
    return str(raw or "").strip()


def resolve_provider_credentials(
    provider_name: str,
    *,
    config: Optional[DataProvidersConfig] = None,
) -> ResolvedProviderCredentials:
    name = _normalize_provider_name(provider_name)
    active_config = config or load_provider_config()
    profile = get_provider_runtime_profile(name)
    entry = active_config.get_provider(name) if active_config else None

    if profile is None:
        return ResolvedProviderCredentials(
            provider_name=name,
            values={},
            presence={},
            missing_required=(),
            sources={},
            env_keys={},
        )

    values: dict[str, str] = {}
    presence: dict[str, bool] = {}
    missing_required: list[str] = []
    sources: dict[str, str] = {}
    env_keys: dict[str, tuple[str, ...]] = {}

    all_credentials = tuple(profile.required_credentials) + tuple(profile.optional_credentials)
    for credential_name in all_credentials:
        env_candidates = _env_candidates(profile, credential_name)
        env_keys[credential_name] = env_candidates
        resolved = ""
        source = "missing"

        for env_key in env_candidates:
            env_val = str(os.environ.get(env_key, "")).strip()
            if env_val:
                resolved = env_val
                source = f"env:{env_key}"
                break

        if not resolved:
            cfg_val = _resolve_config_credential(entry, credential_name)
            if cfg_val:
                resolved = cfg_val
                source = f"config:{_CREDENTIAL_CONFIG_FIELDS.get(credential_name, credential_name.lower())}"

        values[credential_name] = resolved
        present = bool(resolved)
        presence[credential_name] = present
        if credential_name in profile.required_credentials and not present:
            missing_required.append(credential_name)
        sources[credential_name] = source

    return ResolvedProviderCredentials(
        provider_name=name,
        values=values,
        presence=presence,
        missing_required=tuple(missing_required),
        sources=sources,
        env_keys=env_keys,
    )


def get_provider_capabilities(provider_name: str) -> dict[str, Any]:
    name = _normalize_provider_name(provider_name)
    try:
        feature_set = get_provider_feature_set(name)
    except ProviderCapabilityError:
        return {"known": False, "provider_name": name}
    return _feature_set_to_dict(feature_set)


def _feature_set_to_dict(feature_set: ProviderFeatureSet) -> dict[str, Any]:
    return {
        "known": True,
        "provider_name": feature_set.provider_name,
        "implementation_status": feature_set.implementation_status.value,
        "supports_historical_data": feature_set.supports_historical_data,
        "supports_live_quotes": feature_set.supports_live_quotes,
        "supports_intraday_bars": feature_set.supports_intraday_bars,
        "supports_daily_bars": feature_set.supports_daily_bars,
        "supports_instrument_lookup": feature_set.supports_instrument_lookup,
        "supports_order_execution": feature_set.supports_order_execution,
        "supports_snapshot_polling": feature_set.supports_snapshot_polling,
        "supported_segments": list(feature_set.supported_segments),
        "supports_derivatives": feature_set.supports_derivatives,
        "supports_historical_derivatives": feature_set.supports_historical_derivatives,
        "supports_latest_derivatives": feature_set.supports_latest_derivatives,
        "supports_oi": feature_set.supports_oi,
        "supports_market_depth": feature_set.supports_market_depth,
        "instrument_master_available": feature_set.instrument_master_available,
        "notes": feature_set.notes,
    }


def _workflow_requirements_from_mode(
    mode: Optional[str],
    *,
    require_historical_data: Optional[bool],
    require_live_quotes: Optional[bool],
) -> tuple[bool, bool, Optional[str]]:
    if not mode:
        return bool(require_historical_data), bool(require_live_quotes), None

    try:
        from src.runtime.run_profiles import get_run_profile

        profile = get_run_profile(mode)
        historical = (
            profile.requires_historical_data
            if require_historical_data is None
            else bool(require_historical_data)
        )
        live_quotes = (
            profile.requires_live_quotes
            if require_live_quotes is None
            else bool(require_live_quotes)
        )
        return bool(historical), bool(live_quotes), profile.mode.value
    except Exception:
        return bool(require_historical_data), bool(require_live_quotes), str(mode).strip().lower()


def get_provider_readiness_report(
    provider_name: str,
    *,
    config: Optional[DataProvidersConfig] = None,
    session_manager: Optional[ProviderSessionManager] = None,
    require_enabled: bool = True,
    require_historical_data: Optional[bool] = None,
    require_live_quotes: Optional[bool] = None,
    timeframe: Optional[str] = None,
    instrument_type: InstrumentType | str | None = InstrumentType.EQUITY,
    mode: Optional[str] = None,
) -> ProviderReadinessReport:
    name = _normalize_provider_name(provider_name)
    active_config = config or load_provider_config()
    profile = get_provider_runtime_profile(name)
    provider_entry = active_config.get_provider(name)
    configured = provider_entry is not None
    enabled = bool(provider_entry.enabled) if provider_entry else False
    is_default_provider = str(active_config.default_provider).strip().lower() == name

    if profile is None:
        return ProviderReadinessReport(
            provider_name=name,
            display_name=name,
            state=ProviderRuntimeState.UNSUPPORTED,
            reason=f"Provider '{name}' is not registered in the runtime profile registry.",
            enabled=enabled,
            configured=configured,
            is_default_provider=is_default_provider,
            requires_session=False,
            session_status=None,
            can_instantiate=False,
            credentials_required=(),
            credentials_present={},
            missing_credentials=(),
            credential_env_keys={},
            capability_summary=get_provider_capabilities(name),
            workflow_supported=False,
            workflow_requirements={},
        )

    resolved = resolve_provider_credentials(name, config=active_config)
    capability_summary = get_provider_capabilities(name)
    historical_required, live_quotes_required, mode_name = _workflow_requirements_from_mode(
        mode,
        require_historical_data=require_historical_data,
        require_live_quotes=require_live_quotes,
    )
    workflow_requirements = {
        "mode": mode_name,
        "require_historical_data": bool(historical_required),
        "require_live_quotes": bool(live_quotes_required),
        "timeframe": timeframe,
        "instrument_type": (
            instrument_type.value
            if hasattr(instrument_type, "value")
            else str(instrument_type) if instrument_type is not None else None
        ),
    }

    workflow_supported = True
    workflow_error = ""
    try:
        validate_provider_workflow(
            name,
            require_historical_data=bool(historical_required),
            require_live_quotes=bool(live_quotes_required),
            timeframe=timeframe,
            instrument_type=instrument_type,
        )
    except ProviderCapabilityError as exc:
        workflow_supported = False
        workflow_error = str(exc)

    session_status: Optional[str] = None
    manager: ProviderSessionManager | None = None
    if profile.requires_session:
        manager = session_manager or ProviderSessionManager()
        state_obj = manager.get_status(name)
        session_status = str(state_obj.session_status)
        # Session manager currently reads env-only credentials; reconcile this
        # with shared credential resolution (env + config compatibility).
        if (
            session_status == SessionStatus.CREDENTIALS_MISSING.value
            and resolved.is_fully_configured
        ):
            session_status = SessionStatus.NOT_CONFIGURED.value

    if require_enabled and configured and not enabled:
        return ProviderReadinessReport(
            provider_name=name,
            display_name=profile.display_name,
            state=ProviderRuntimeState.DISABLED,
            reason=(
                f"Provider '{name}' is disabled in config/data_providers.yaml. "
                "Enable it before running this workflow."
            ),
            enabled=enabled,
            configured=configured,
            is_default_provider=is_default_provider,
            requires_session=profile.requires_session,
            session_status=session_status,
            can_instantiate=False,
            credentials_required=profile.required_credentials,
            credentials_present=resolved.presence,
            missing_credentials=resolved.missing_required,
            credential_env_keys=resolved.env_keys,
            capability_summary=capability_summary,
            workflow_supported=workflow_supported,
            workflow_requirements=workflow_requirements,
        )

    if profile.required_credentials and not resolved.is_fully_configured:
        missing = ", ".join(resolved.missing_required)
        return ProviderReadinessReport(
            provider_name=name,
            display_name=profile.display_name,
            state=ProviderRuntimeState.MISSING_SECRETS,
            reason=(
                f"Provider '{name}' is missing required credentials: {missing}. "
                "Configure credentials in environment/.env before running."
            ),
            enabled=enabled,
            configured=configured,
            is_default_provider=is_default_provider,
            requires_session=profile.requires_session,
            session_status=session_status,
            can_instantiate=False,
            credentials_required=profile.required_credentials,
            credentials_present=resolved.presence,
            missing_credentials=resolved.missing_required,
            credential_env_keys=resolved.env_keys,
            capability_summary=capability_summary,
            workflow_supported=workflow_supported,
            workflow_requirements=workflow_requirements,
        )

    if not workflow_supported:
        return ProviderReadinessReport(
            provider_name=name,
            display_name=profile.display_name,
            state=ProviderRuntimeState.MISCONFIGURED,
            reason=workflow_error,
            enabled=enabled,
            configured=configured,
            is_default_provider=is_default_provider,
            requires_session=profile.requires_session,
            session_status=session_status,
            can_instantiate=False,
            credentials_required=profile.required_credentials,
            credentials_present=resolved.presence,
            missing_credentials=resolved.missing_required,
            credential_env_keys=resolved.env_keys,
            capability_summary=capability_summary,
            workflow_supported=workflow_supported,
            workflow_requirements=workflow_requirements,
        )

    # Sync runtime readiness with provider session validation logic when
    # credentials are present but status has not yet been validated in this process.
    if (
        profile.requires_session
        and session_status == SessionStatus.NOT_CONFIGURED.value
        and profile.required_credentials
        and resolved.is_fully_configured
        and manager is not None
    ):
        validated_state = manager.validate_session(name)
        session_status = str(validated_state.session_status)

    invalid_session_statuses = {
        SessionStatus.INVALID.value,
        SessionStatus.EXPIRED.value,
        SessionStatus.ERROR.value,
    }
    if profile.requires_session and session_status in invalid_session_statuses:
        return ProviderReadinessReport(
            provider_name=name,
            display_name=profile.display_name,
            state=ProviderRuntimeState.SESSION_INVALID,
            reason=(
                f"Provider '{name}' session status is '{session_status}'. "
                "Revalidate the provider session."
            ),
            enabled=enabled,
            configured=configured,
            is_default_provider=is_default_provider,
            requires_session=profile.requires_session,
            session_status=session_status,
            can_instantiate=False,
            credentials_required=profile.required_credentials,
            credentials_present=resolved.presence,
            missing_credentials=resolved.missing_required,
            credential_env_keys=resolved.env_keys,
            capability_summary=capability_summary,
            workflow_supported=workflow_supported,
            workflow_requirements=workflow_requirements,
        )

    if profile.requires_session and session_status != SessionStatus.ACTIVE.value:
        return ProviderReadinessReport(
            provider_name=name,
            display_name=profile.display_name,
            state=ProviderRuntimeState.PARTIAL,
            reason=(
                f"Provider '{name}' credentials are present but session status is "
                f"'{session_status or SessionStatus.NOT_CONFIGURED.value}'."
            ),
            enabled=enabled,
            configured=configured,
            is_default_provider=is_default_provider,
            requires_session=profile.requires_session,
            session_status=session_status,
            can_instantiate=True,
            credentials_required=profile.required_credentials,
            credentials_present=resolved.presence,
            missing_credentials=resolved.missing_required,
            credential_env_keys=resolved.env_keys,
            capability_summary=capability_summary,
            workflow_supported=workflow_supported,
            workflow_requirements=workflow_requirements,
        )

    implementation_status = str(
        capability_summary.get("implementation_status", "")
    ).strip().lower()
    state = ProviderRuntimeState.READY
    reason = f"Provider '{name}' is ready."
    if implementation_status == "partial":
        reason = (
            f"Provider '{name}' is ready for the requested workflow "
            "(provider capability status: partial)."
        )
    return ProviderReadinessReport(
        provider_name=name,
        display_name=profile.display_name,
        state=state,
        reason=reason,
        enabled=enabled,
        configured=configured,
        is_default_provider=is_default_provider,
        requires_session=profile.requires_session,
        session_status=session_status,
        can_instantiate=True,
        credentials_required=profile.required_credentials,
        credentials_present=resolved.presence,
        missing_credentials=resolved.missing_required,
        credential_env_keys=resolved.env_keys,
        capability_summary=capability_summary,
        workflow_supported=workflow_supported,
        workflow_requirements=workflow_requirements,
    )


def get_provider_runtime_status(
    provider_name: str,
    **kwargs: Any,
) -> ProviderReadinessReport:
    return get_provider_readiness_report(provider_name, **kwargs)


def can_create_provider(
    provider_name: str,
    *,
    config: Optional[DataProvidersConfig] = None,
    session_manager: Optional[ProviderSessionManager] = None,
    require_enabled: bool = True,
    require_historical_data: Optional[bool] = None,
    require_live_quotes: Optional[bool] = None,
    timeframe: Optional[str] = None,
    instrument_type: InstrumentType | str | None = InstrumentType.EQUITY,
    mode: Optional[str] = None,
) -> bool:
    report = get_provider_readiness_report(
        provider_name,
        config=config,
        session_manager=session_manager,
        require_enabled=require_enabled,
        require_historical_data=require_historical_data,
        require_live_quotes=require_live_quotes,
        timeframe=timeframe,
        instrument_type=instrument_type,
        mode=mode,
    )
    return bool(report.can_instantiate)


def list_all_provider_reports(
    *,
    config: Optional[DataProvidersConfig] = None,
    session_manager: Optional[ProviderSessionManager] = None,
    require_enabled: bool = False,
    require_historical_data: Optional[bool] = None,
    require_live_quotes: Optional[bool] = None,
    timeframe: Optional[str] = None,
    instrument_type: InstrumentType | str | None = InstrumentType.EQUITY,
    mode: Optional[str] = None,
) -> list[ProviderReadinessReport]:
    active_config = config or load_provider_config()
    manager = session_manager or ProviderSessionManager()
    names = set(active_config.providers.keys()) | set(_build_default_profiles().keys()) | set(
        _PROFILE_OVERRIDES.keys()
    )
    reports: list[ProviderReadinessReport] = []
    for name in sorted(names):
        reports.append(
            get_provider_readiness_report(
                name,
                config=active_config,
                session_manager=manager,
                require_enabled=require_enabled,
                require_historical_data=require_historical_data,
                require_live_quotes=require_live_quotes,
                timeframe=timeframe,
                instrument_type=instrument_type,
                mode=mode,
            )
        )
    return reports
