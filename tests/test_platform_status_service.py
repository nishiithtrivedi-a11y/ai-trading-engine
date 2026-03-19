"""Tests for src.api.services.platform_status_service module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from src.api.services.market_session_service import MarketSessionPhase
from src.api.services.platform_status_service import (
    FeatureAvailability,
    PlatformStatus,
    _compute_feature_availability,
    get_platform_status,
)
from src.providers.credential_store import CredentialStore
from src.providers.models import ProviderType, SessionStatus
from src.providers.session_manager import ProviderSessionManager


def _make_manager(tmp_path: Path) -> ProviderSessionManager:
    return ProviderSessionManager(
        credential_store=CredentialStore(env_file_path=tmp_path / ".env"),
    )


# ---------------------------------------------------------------------------
# Feature availability computation
# ---------------------------------------------------------------------------


def test_feature_realtime_when_broker_source_and_market_open() -> None:
    fa = _compute_feature_availability(
        runtime_source="zerodha",
        connected=1,
        market_phase=MarketSessionPhase.OPEN,
    )
    assert fa == FeatureAvailability.REALTIME_ANALYSIS


def test_feature_fallback_when_csv_but_provider_connected() -> None:
    fa = _compute_feature_availability(
        runtime_source="csv",
        connected=1,
        market_phase=MarketSessionPhase.OPEN,
    )
    assert fa == FeatureAvailability.FALLBACK_ACTIVE


def test_feature_post_market_when_post_close() -> None:
    fa = _compute_feature_availability(
        runtime_source="csv",
        connected=0,
        market_phase=MarketSessionPhase.POST_CLOSE,
    )
    assert fa == FeatureAvailability.POST_MARKET


def test_feature_offline_when_closed_and_no_provider() -> None:
    fa = _compute_feature_availability(
        runtime_source="csv",
        connected=0,
        market_phase=MarketSessionPhase.CLOSED,
    )
    assert fa == FeatureAvailability.OFFLINE_ANALYSIS


def test_feature_offline_weekend() -> None:
    fa = _compute_feature_availability(
        runtime_source="csv",
        connected=0,
        market_phase=MarketSessionPhase.WEEKEND,
    )
    assert fa == FeatureAvailability.OFFLINE_ANALYSIS


def test_feature_fallback_indian_csv_with_session() -> None:
    fa = _compute_feature_availability(
        runtime_source="indian_csv",
        connected=2,
        market_phase=MarketSessionPhase.OPEN,
    )
    assert fa == FeatureAvailability.FALLBACK_ACTIVE


# ---------------------------------------------------------------------------
# Full status snapshot
# ---------------------------------------------------------------------------


def test_platform_status_returns_all_keys(tmp_path: Path) -> None:
    """get_platform_status should return a dict with all expected keys."""
    for key in ("ZERODHA_API_KEY", "ZERODHA_API_SECRET", "ZERODHA_ACCESS_TOKEN"):
        os.environ.pop(key, None)

    mgr = _make_manager(tmp_path)
    status = get_platform_status(session_manager=mgr)

    assert isinstance(status, PlatformStatus)
    d = status.to_dict()
    expected_keys = {
        "runtime_data_source",
        "connected_sessions",
        "total_sessions",
        "market_session",
        "feature_availability",
        "feature_availability_label",
        "provider_statuses",
        "execution_enabled",
    }
    assert set(d.keys()) == expected_keys


def test_execution_always_disabled(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    status = get_platform_status(session_manager=mgr)
    assert status.execution_enabled is False
    assert status.to_dict()["execution_enabled"] is False


def test_no_active_sessions_by_default(tmp_path: Path) -> None:
    for key in (
        "ZERODHA_API_KEY", "ZERODHA_API_SECRET", "ZERODHA_ACCESS_TOKEN",
        "DHAN_CLIENT_ID", "DHAN_ACCESS_TOKEN",
        "UPSTOX_API_KEY", "UPSTOX_API_SECRET", "UPSTOX_ACCESS_TOKEN",
    ):
        os.environ.pop(key, None)

    mgr = _make_manager(tmp_path)
    status = get_platform_status(session_manager=mgr)
    assert status.connected_sessions == 0
    assert status.total_sessions == 3


def test_provider_status_roles(tmp_path: Path) -> None:
    """Verify that when no sessions are active, roles are 'offline'."""
    for key in (
        "ZERODHA_API_KEY", "ZERODHA_API_SECRET", "ZERODHA_ACCESS_TOKEN",
        "DHAN_CLIENT_ID", "DHAN_ACCESS_TOKEN",
        "UPSTOX_API_KEY", "UPSTOX_API_SECRET", "UPSTOX_ACCESS_TOKEN",
    ):
        os.environ.pop(key, None)

    mgr = _make_manager(tmp_path)
    status = get_platform_status(session_manager=mgr)

    roles = {p.provider_type: p.runtime_role for p in status.provider_statuses}
    # Without credentials, all should be "offline"
    for role in roles.values():
        assert role == "offline"
