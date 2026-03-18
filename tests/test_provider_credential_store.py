"""Tests for src.providers.credential_store module."""

from __future__ import annotations

import os
from pathlib import Path

from src.providers.credential_store import CredentialStore
from src.providers.models import ProviderType


def test_has_credentials_all_missing(tmp_path: Path) -> None:
    store = CredentialStore(env_file_path=tmp_path / ".env")
    # Ensure env vars are cleared
    for key in ("ZERODHA_API_KEY", "ZERODHA_API_SECRET", "ZERODHA_ACCESS_TOKEN"):
        os.environ.pop(key, None)
    assert store.has_credentials(ProviderType.ZERODHA) is False


def test_has_credentials_with_env_vars(tmp_path: Path) -> None:
    store = CredentialStore(env_file_path=tmp_path / ".env")
    os.environ["ZERODHA_API_KEY"] = "test_key"
    os.environ["ZERODHA_API_SECRET"] = "test_secret"
    os.environ["ZERODHA_ACCESS_TOKEN"] = "test_token"
    try:
        assert store.has_credentials(ProviderType.ZERODHA) is True
    finally:
        os.environ.pop("ZERODHA_API_KEY", None)
        os.environ.pop("ZERODHA_API_SECRET", None)
        os.environ.pop("ZERODHA_ACCESS_TOKEN", None)


def test_get_masked_indicators(tmp_path: Path) -> None:
    store = CredentialStore(env_file_path=tmp_path / ".env")
    os.environ["ZERODHA_API_KEY"] = "abcdef123456"
    os.environ.pop("ZERODHA_API_SECRET", None)
    os.environ.pop("ZERODHA_ACCESS_TOKEN", None)
    try:
        indicators = store.get_masked_indicators(ProviderType.ZERODHA)
        assert "456" in indicators["API_KEY"]  # last 3 chars visible
        assert indicators["API_SECRET"] == "Not Set"
        assert "abcdef123456" not in str(indicators)  # raw value never exposed
    finally:
        os.environ.pop("ZERODHA_API_KEY", None)


def test_store_credential_updates_env(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    store = CredentialStore(env_file_path=env_file)
    os.environ.pop("DHAN_CLIENT_ID", None)

    stored = store.store_credential(ProviderType.DHAN, "CLIENT_ID", "test_client_id")
    assert stored is True
    assert os.environ.get("DHAN_CLIENT_ID") == "test_client_id"
    assert env_file.exists()
    content = env_file.read_text()
    assert "DHAN_CLIENT_ID=test_client_id" in content

    os.environ.pop("DHAN_CLIENT_ID", None)


def test_store_credential_rejects_unknown(tmp_path: Path) -> None:
    store = CredentialStore(env_file_path=tmp_path / ".env")
    stored = store.store_credential(ProviderType.ZERODHA, "NONEXISTENT_KEY", "val")
    assert stored is False


def test_mask_value() -> None:
    assert CredentialStore._mask_value("") == "Not Set"
    assert CredentialStore._mask_value("ab") == "••"
    assert CredentialStore._mask_value("abcdef") == "•••def"


def test_get_credential_status(tmp_path: Path) -> None:
    store = CredentialStore(env_file_path=tmp_path / ".env")
    os.environ["UPSTOX_API_KEY"] = "key"
    os.environ.pop("UPSTOX_API_SECRET", None)
    os.environ.pop("UPSTOX_ACCESS_TOKEN", None)
    try:
        status = store.get_credential_status(ProviderType.UPSTOX)
        assert status["API_KEY"] is True
        assert status["API_SECRET"] is False
    finally:
        os.environ.pop("UPSTOX_API_KEY", None)
