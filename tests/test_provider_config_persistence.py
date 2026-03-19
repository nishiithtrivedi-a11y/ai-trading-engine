"""Tests for provider config persistence hardening."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.data.provider_config import DataProvidersConfig, ProviderEntry


def test_save_config_scrubs_secret_fields(tmp_path: Path) -> None:
    cfg = DataProvidersConfig(
        default_provider="zerodha",
        providers={
            "zerodha": ProviderEntry(
                enabled=True,
                api_key="real_key",
                api_secret="real_secret",
                access_token="real_token",
                base_url="https://api.kite.trade",
            ),
            "dhan": ProviderEntry(
                enabled=False,
                api_key="client_id",
                access_token="access_token",
                base_url="https://api.dhan.co",
            ),
        },
    )
    target = tmp_path / "providers.yaml"

    assert cfg.save_config(target) is True

    raw_text = target.read_text(encoding="utf-8")
    assert "real_key" not in raw_text
    assert "real_secret" not in raw_text
    assert "real_token" not in raw_text
    assert "client_id" not in raw_text

    persisted = yaml.safe_load(raw_text)
    assert persisted["default_provider"] == "zerodha"
    assert persisted["providers"]["zerodha"]["base_url"] == "https://api.kite.trade"
    assert persisted["providers"]["zerodha"]["api_key"] == ""
    assert persisted["providers"]["zerodha"]["api_secret"] == ""
    assert persisted["providers"]["zerodha"]["access_token"] == ""
