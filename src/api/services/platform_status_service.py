"""
Unified platform status aggregation service.

Combines four independent concepts into a single truthful snapshot:
1. Provider Session Status   (from ProviderSessionManager)
2. Active Runtime Data Source (from DataProvidersConfig / YAML)
3. Market Session State       (from MarketSessionService)
4. Feature Availability Mode  (computed from 1+2+3)

SAFETY: This module is read-only — no execution paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from src.api.services.market_session_service import (
    MarketSessionPhase,
    MarketSessionState,
    get_market_session_state,
)
from src.data.provider_config import load_provider_config
from src.data.provider_runtime import list_all_provider_reports
from src.providers.models import SessionStatus
from src.providers.session_manager import ProviderSessionManager


class FeatureAvailability(str, Enum):
    """What the platform can safely offer right now."""
    REALTIME_ANALYSIS = "realtime_analysis"
    POST_MARKET = "post_market"
    OFFLINE_ANALYSIS = "offline_analysis"
    FALLBACK_ACTIVE = "fallback_active"
    PRIMARY_OFFLINE = "primary_offline"
    SESSION_READY = "session_ready"


# Labels shown in the UI for each mode
_FEATURE_LABELS: dict[FeatureAvailability, str] = {
    FeatureAvailability.REALTIME_ANALYSIS: "Realtime-safe analysis available",
    FeatureAvailability.POST_MARKET: "Post-market workflows available",
    FeatureAvailability.OFFLINE_ANALYSIS: "Offline analysis only",
    FeatureAvailability.FALLBACK_ACTIVE: "Fallback data source active",
    FeatureAvailability.PRIMARY_OFFLINE: "Primary provider offline — In CSV Fallback",
    FeatureAvailability.SESSION_READY: "Active session available — Manual Promotion Required",
}


def _load_runtime_data_source() -> str:
    """Read the active runtime data source from shared provider config."""
    try:
        return str(load_provider_config().default_provider).strip().lower() or "csv"
    except Exception:
        return "csv"


@dataclass
class ProviderDiagnosticEntry:
    """Enriched per-provider status combining session + config state."""
    provider_type: str
    display_name: str
    session_status: str
    is_runtime_primary: bool
    config_enabled: bool
    last_validated: Optional[str] = None
    diagnostics_summary: str = ""
    runtime_role: str = ""     # "primary" / "connected" / "configured" / "offline"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_type": self.provider_type,
            "display_name": self.display_name,
            "session_status": self.session_status,
            "is_runtime_primary": self.is_runtime_primary,
            "config_enabled": self.config_enabled,
            "last_validated": self.last_validated,
            "diagnostics_summary": self.diagnostics_summary,
            "runtime_role": self.runtime_role,
        }


@dataclass
class PlatformStatus:
    """Full platform status snapshot."""
    runtime_data_source: str
    connected_sessions: int
    total_sessions: int
    market_session: MarketSessionState
    feature_availability: FeatureAvailability
    feature_availability_label: str
    provider_statuses: list[ProviderDiagnosticEntry]
    execution_enabled: bool = False  # Always False — structural safety

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_data_source": self.runtime_data_source,
            "connected_sessions": self.connected_sessions,
            "total_sessions": self.total_sessions,
            "market_session": self.market_session.to_dict(),
            "feature_availability": self.feature_availability.value,
            "feature_availability_label": self.feature_availability_label,
            "provider_statuses": [p.to_dict() for p in self.provider_statuses],
            "execution_enabled": self.execution_enabled,
        }


def get_platform_status(
    session_manager: Optional[ProviderSessionManager] = None,
) -> PlatformStatus:
    """Build a truthful, unified platform status snapshot.

    This is the single source of truth consumed by the frontend for
    TopNav, StatusStrip, Diagnostics, and feature-gating logic.
    """
    if session_manager is None:
        session_manager = ProviderSessionManager()

    # 1. Runtime data source from config
    runtime_source = _load_runtime_data_source()

    provider_config = load_provider_config()
    reports = list_all_provider_reports(
        config=provider_config,
        session_manager=session_manager,
        require_enabled=False,
    )

    session_reports = [report for report in reports if report.requires_session]
    connected = sum(
        1
        for report in session_reports
        if str(report.session_status or "").strip().lower() == SessionStatus.ACTIVE.value
    )
    total = len(session_reports)

    # Build per-provider diagnostic entries
    provider_statuses: list[ProviderDiagnosticEntry] = []
    for report in session_reports:
        is_primary = report.provider_name == runtime_source
        config_enabled = bool(provider_config.is_provider_enabled(report.provider_name))
        session_status = str(report.session_status or SessionStatus.NOT_CONFIGURED.value)
        is_active = session_status == SessionStatus.ACTIVE.value

        # Richer role and summary
        if is_primary:
            if is_active:
                role = "primary"
                summary = "Selected as primary runtime source. Session ACTIVE."
            elif config_enabled:
                role = "primary_unavailable"
                summary = (
                    "Selected as primary but session is "
                    f"{session_status}. Falling back to CSV. {report.reason}"
                )
            else:
                role = "primary_misconfigured"
                summary = "Selected as primary but not enabled in config. Falling back to CSV."
        elif is_active:
            role = "eligible"
            summary = "Session active and ready. Not currently selected as primary source."
        elif config_enabled:
            role = "configured"
            summary = f"Configured but session {session_status}. {report.reason}"
        else:
            role = "offline"
            summary = report.reason

        provider_statuses.append(
            ProviderDiagnosticEntry(
                provider_type=report.provider_name,
                display_name=report.display_name,
                session_status=session_status,
                is_runtime_primary=is_primary,
                config_enabled=config_enabled,
                last_validated=None,
                diagnostics_summary=summary,
                runtime_role=role,
            )
        )

    # 5. Market session
    market = get_market_session_state()

    # 6. Feature availability computation
    feature = _compute_feature_availability(
        runtime_source=runtime_source,
        provider_statuses=provider_statuses,
        market_phase=market.phase,
    )

    return PlatformStatus(
        runtime_data_source=runtime_source,
        connected_sessions=connected,
        total_sessions=total,
        market_session=market,
        feature_availability=feature,
        feature_availability_label=_FEATURE_LABELS[feature],
        provider_statuses=provider_statuses,
    )


def _compute_feature_availability(
    runtime_source: str,
    market_phase: MarketSessionPhase,
    provider_statuses: Optional[list[ProviderDiagnosticEntry]] = None,
    connected: Optional[int] = None,
) -> FeatureAvailability:
    """
    Determine what features can safely be used right now.

    Backward compatibility:
    - Legacy callers may provide ``connected`` without ``provider_statuses``.
    - New callers should provide ``provider_statuses`` for richer truthfulness.
    """
    if provider_statuses is None:
        connected_count = max(0, int(connected or 0))
        has_broker_source = runtime_source not in ("csv", "indian_csv")
        market_open = market_phase == MarketSessionPhase.OPEN

        if has_broker_source:
            if connected_count > 0:
                if market_open:
                    return FeatureAvailability.REALTIME_ANALYSIS
                return FeatureAvailability.POST_MARKET
            return FeatureAvailability.PRIMARY_OFFLINE

        if connected_count > 0:
            return FeatureAvailability.FALLBACK_ACTIVE

        if market_phase in (
            MarketSessionPhase.POST_CLOSE,
            MarketSessionPhase.PRE_OPEN,
        ):
            return FeatureAvailability.POST_MARKET

        return FeatureAvailability.OFFLINE_ANALYSIS

    has_broker_source = runtime_source not in ("csv", "indian_csv")
    market_open = market_phase == MarketSessionPhase.OPEN

    # Check if the primary is actually active
    primary_entry = next((p for p in provider_statuses if p.is_runtime_primary), None)
    primary_active = primary_entry and primary_entry.session_status == SessionStatus.ACTIVE.value

    if has_broker_source:
        if primary_active:
            if market_open:
                return FeatureAvailability.REALTIME_ANALYSIS
            else:
                return FeatureAvailability.POST_MARKET
        else:
            # Selected primary is broker, but it's not active -> fallback mode
            return FeatureAvailability.PRIMARY_OFFLINE

    # CSV mode
    any_active = any(p.session_status == SessionStatus.ACTIVE.value for p in provider_statuses if p.provider_type not in ("csv", "indian_csv"))
    if any_active:
        # Broker connected but runtime still on CSV
        return FeatureAvailability.SESSION_READY

    if market_phase in (
        MarketSessionPhase.POST_CLOSE,
        MarketSessionPhase.PRE_OPEN,
    ):
        return FeatureAvailability.POST_MARKET

    return FeatureAvailability.OFFLINE_ANALYSIS
