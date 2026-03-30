"""
API routes for provider health and diagnostics.

Uses the shared provider runtime readiness layer so UI diagnostics and
engine workflows evaluate provider state from the same source of truth.

SAFETY: Read-only and execution-disabled.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.api.routers.provider_sessions import _session_manager
from src.api.services.market_session_service import get_market_session_state
from src.data.provider_config import load_provider_config
from src.data.provider_runtime import (
    ProviderReadinessReport,
    ProviderRuntimeState,
    list_all_provider_reports,
)

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


def _status_payload(
    report: ProviderReadinessReport,
    *,
    is_primary: bool,
    config_enabled: bool,
    default_provider: str,
) -> tuple[str, str, str, str]:
    session_active = str(report.session_status or "").strip().lower() == "active"

    if is_primary:
        if session_active:
            return (
                "active_primary",
                "Read-only check",
                "Primary runtime source with active session.",
                "active_primary",
            )
        if report.can_instantiate:
            return (
                "primary_ready",
                "Configured",
                (
                    "Primary runtime source is creatable but session is not active "
                    f"(session={report.session_status or 'not_configured'})."
                ),
                "primary_ready",
            )
        if report.state == ProviderRuntimeState.DISABLED:
            return (
                "primary_misconfigured",
                "N/A",
                "Primary source is disabled in config; fallback behavior applies.",
                "primary_misconfigured",
            )
        return (
            "primary_unavailable",
            "N/A",
            f"Primary source unavailable: {report.reason}",
            "primary_unavailable",
        )

    if session_active:
        return (
            "session_active",
            "Read-only check",
            f"Session active and eligible for promotion (primary: {default_provider}).",
            "session_active",
        )
    if config_enabled and report.can_instantiate:
        return (
            "healthy",
            "Configured",
            "Enabled in config and workflow-ready.",
            "healthy",
        )
    if report.state == ProviderRuntimeState.MISSING_SECRETS:
        return (
            "configured",
            "N/A",
            "Configured but credentials are incomplete.",
            "configured",
        )
    return (
        "offline",
        "N/A",
        report.reason,
        "offline",
    )


@router.get("/health")
def get_providers_health() -> dict[str, Any]:
    """Return provider health from the shared runtime readiness model."""
    provider_config = load_provider_config()
    default_provider = str(provider_config.default_provider).strip().lower()
    reports = {
        report.provider_name: report
        for report in list_all_provider_reports(
            config=provider_config,
            session_manager=_session_manager,
            require_enabled=False,
        )
    }

    diagnostics: list[dict[str, Any]] = []
    for provider_name, provider_entry in provider_config.providers.items():
        report = reports.get(provider_name)
        if report is None:
            continue

        status, latency, details, runtime_role = _status_payload(
            report,
            is_primary=(provider_name == default_provider),
            config_enabled=bool(provider_entry.enabled),
            default_provider=default_provider,
        )
        diagnostics.append(
            {
                "name": provider_name,
                "type": "market_data",
                "enabled": bool(provider_entry.enabled),
                "status": status,
                "latency": latency,
                "details": details,
                "session_status": report.session_status,
                "runtime_state": report.state.value,
                "runtime_role": runtime_role,
                "reason": report.reason,
            }
        )

    analysis_cfg = provider_config.analysis_providers.normalized()
    for module_name, provider_name in analysis_cfg.items():
        if module_name == "allow_derived_sentiment_fallback":
            continue
        if isinstance(provider_name, str) and provider_name != "none":
            diagnostics.append(
                {
                    "name": provider_name,
                    "type": f"analysis_{module_name}",
                    "enabled": True,
                    "status": "healthy",
                    "latency": "Simulated",
                    "details": f"Plugin provider for {module_name} (no live latency probe).",
                    "session_status": None,
                }
            )

    return {
        "default_provider": default_provider,
        "diagnostics": diagnostics,
        "market_session": get_market_session_state().to_dict(),
    }

