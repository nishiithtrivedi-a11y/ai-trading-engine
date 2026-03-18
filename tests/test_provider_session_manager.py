"""Tests for src.providers.session_manager module."""

from __future__ import annotations

import os
from pathlib import Path

from src.providers.credential_store import CredentialStore
from src.providers.models import ProviderType, SessionStatus
from src.providers.session_manager import ProviderSessionManager


def _make_manager(tmp_path: Path) -> ProviderSessionManager:
    return ProviderSessionManager(
        credential_store=CredentialStore(env_file_path=tmp_path / ".env"),
    )


def test_get_all_statuses_returns_all_providers(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    statuses = mgr.get_all_statuses()
    # Should return Zerodha, Dhan, Upstox
    assert len(statuses) == 3
    types = {s.provider_type for s in statuses}
    assert "zerodha" in types
    assert "dhan" in types
    assert "upstox" in types


def test_status_without_credentials(tmp_path: Path) -> None:
    # Clear any env vars
    for key in ("ZERODHA_API_KEY", "ZERODHA_API_SECRET", "ZERODHA_ACCESS_TOKEN"):
        os.environ.pop(key, None)

    mgr = _make_manager(tmp_path)
    state = mgr.get_status(ProviderType.ZERODHA)
    assert state.session_status == SessionStatus.CREDENTIALS_MISSING.value
    assert state.credentials_present is False


def test_validate_with_credentials(tmp_path: Path) -> None:
    os.environ["DHAN_CLIENT_ID"] = "test_id"
    os.environ["DHAN_ACCESS_TOKEN"] = "test_token"
    try:
        mgr = _make_manager(tmp_path)
        state = mgr.validate_session(ProviderType.DHAN)
        assert state.session_status == SessionStatus.ACTIVE.value
        assert state.credentials_present is True
        assert state.last_validated is not None
    finally:
        os.environ.pop("DHAN_CLIENT_ID", None)
        os.environ.pop("DHAN_ACCESS_TOKEN", None)


def test_validate_without_credentials(tmp_path: Path) -> None:
    for key in ("ZERODHA_API_KEY", "ZERODHA_API_SECRET", "ZERODHA_ACCESS_TOKEN"):
        os.environ.pop(key, None)
    mgr = _make_manager(tmp_path)
    state = mgr.validate_session(ProviderType.ZERODHA)
    assert state.session_status == SessionStatus.CREDENTIALS_MISSING.value


def test_configure_credential(tmp_path: Path) -> None:
    os.environ.pop("UPSTOX_API_KEY", None)
    os.environ.pop("UPSTOX_API_SECRET", None)
    os.environ.pop("UPSTOX_ACCESS_TOKEN", None)

    mgr = _make_manager(tmp_path)
    state = mgr.configure_credential(ProviderType.UPSTOX, "API_KEY", "new_key_value")
    # Should have stored the credential
    assert os.environ.get("UPSTOX_API_KEY") == "new_key_value"
    # Session state should reflect partial creds
    assert "new_key_value" not in str(state.to_dict())  # raw value never in response

    os.environ.pop("UPSTOX_API_KEY", None)


def test_configure_invalid_credential(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    state = mgr.configure_credential(ProviderType.ZERODHA, "NONEXISTENT", "val")
    assert state.session_status == SessionStatus.ERROR.value


def test_string_provider_type(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    state = mgr.get_status("zerodha")
    assert state.provider_type == "zerodha"


def test_unknown_provider(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    state = mgr.get_status("nonexistent_broker")
    assert state.session_status == SessionStatus.NOT_CONFIGURED.value
