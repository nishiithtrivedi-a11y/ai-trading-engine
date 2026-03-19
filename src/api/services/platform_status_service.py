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
from src.providers.models import PROVIDER_REGISTRY, SessionStatus
from src.providers.session_manager import ProviderSessionManager


class FeatureAvailability(str, Enum):
    """What the platform can safely offer right now."""
    REALTIME_ANALYSIS = "realtime_analysis"
    POST_MARKET = "post_market"
    OFFLINE_ANALYSIS = "offline_analysis"
    FALLBACK_ACTIVE = "fallback_active"


# Labels shown in the UI for each mode
_FEATURE_LABELS: dict[FeatureAvailability, str] = {
    FeatureAvailability.REALTIME_ANALYSIS: "Realtime-safe analysis available",
    FeatureAvailability.POST_MARKET: "Post-market workflows available",
    FeatureAvailability.OFFLINE_ANALYSIS: "Offline analysis only",
    FeatureAvailability.FALLBACK_ACTIVE: "Fallback data source — provider connected but not primary",
}


def _load_runtime_data_source() -> str:
    """Read the active runtime data source from config/data_providers.yaml."""
    from pathlib import Path

    import yaml

    config_path = Path("config/data_providers.yaml")
    if not config_path.exists():
        return "csv"
    try:
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}
        return raw.get("default_provider", "csv")
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

    # 2. Provider sessions
    sessions = session_manager.get_all_statuses()
    connected = sum(
        1 for s in sessions if s.session_status == SessionStatus.ACTIVE.value
    )
    total = len(sessions)

    # 3. Config-enabled providers (from YAML)
    from pathlib import Path
    import yaml

    config_path = Path("config/data_providers.yaml")
    enabled_providers: set[str] = set()
    if config_path.exists():
        try:
            with open(config_path) as f:
                raw = yaml.safe_load(f) or {}
            for pname, pdetails in raw.get("providers", {}).items():
                if isinstance(pdetails, dict) and pdetails.get("enabled"):
                    enabled_providers.add(pname)
        except Exception:
            pass

    # 4. Build per-provider diagnostic entries
    provider_statuses: list[ProviderDiagnosticEntry] = []
    for s in sessions:
        is_primary = s.provider_type == runtime_source
        config_enabled = s.provider_type in enabled_providers
        is_active = s.session_status == SessionStatus.ACTIVE.value

        if is_primary and (config_enabled or is_active):
            role = "primary"
        elif is_active:
            role = "connected"
        elif config_enabled:
            role = "configured"
        else:
            role = "offline"

        summary = s.diagnostics_summary
        if is_active and not is_primary:
            summary = (
                f"Session active — not currently primary runtime source "
                f"(primary: {runtime_source}). {summary}"
            )

        provider_statuses.append(ProviderDiagnosticEntry(
            provider_type=s.provider_type,
            display_name=s.display_name,
            session_status=s.session_status,
            is_runtime_primary=is_primary,
            config_enabled=config_enabled,
            last_validated=s.last_validated,
            diagnostics_summary=summary,
            runtime_role=role,
        ))

    # 5. Market session
    market = get_market_session_state()

    # 6. Feature availability computation
    feature = _compute_feature_availability(
        runtime_source=runtime_source,
        connected=connected,
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
    connected: int,
    market_phase: MarketSessionPhase,
) -> FeatureAvailability:
    """Determine what features can safely be used right now."""
    has_broker_source = runtime_source not in ("csv", "indian_csv")
    market_open = market_phase == MarketSessionPhase.OPEN

    if has_broker_source and market_open:
        return FeatureAvailability.REALTIME_ANALYSIS

    if connected > 0 and runtime_source in ("csv", "indian_csv"):
        # Provider is connected but runtime still on CSV
        return FeatureAvailability.FALLBACK_ACTIVE

    if market_phase in (
        MarketSessionPhase.POST_CLOSE,
        MarketSessionPhase.PRE_OPEN,
    ):
        return FeatureAvailability.POST_MARKET

    return FeatureAvailability.OFFLINE_ANALYSIS
