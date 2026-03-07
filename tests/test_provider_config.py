"""Tests for data provider configuration."""

import os
from pathlib import Path
from unittest import mock

import pytest

from src.data.provider_config import (
    DataProvidersConfig,
    ProviderCredentials,
    ProviderEntry,
    load_provider_config,
    _apply_env_overrides,
)


class TestProviderCredentials:

    def test_empty_credentials_not_configured(self):
        creds = ProviderCredentials()
        assert not creds.is_configured

    def test_partial_credentials_not_configured(self):
        creds = ProviderCredentials(api_key="key", api_secret="")
        assert not creds.is_configured

    def test_full_credentials_configured(self):
        creds = ProviderCredentials(
            api_key="key", api_secret="secret", access_token="token"
        )
        assert creds.is_configured


class TestProviderEntry:

    def test_defaults(self):
        entry = ProviderEntry()
        assert entry.enabled is True
        assert entry.data_dir == "data/"
        assert entry.timezone == "Asia/Kolkata"

    def test_get_credentials(self):
        entry = ProviderEntry(api_key="k", api_secret="s", access_token="t")
        creds = entry.get_credentials()
        assert creds.api_key == "k"
        assert creds.api_secret == "s"
        assert creds.access_token == "t"
        assert creds.is_configured


class TestDataProvidersConfig:

    def test_default_config(self):
        config = DataProvidersConfig()
        assert config.default_provider == "csv"
        assert config.providers == {}

    def test_get_provider_returns_none_for_missing(self):
        config = DataProvidersConfig()
        assert config.get_provider("zerodha") is None

    def test_get_provider_returns_entry(self):
        config = DataProvidersConfig(
            providers={"csv": ProviderEntry(enabled=True)}
        )
        entry = config.get_provider("csv")
        assert entry is not None
        assert entry.enabled is True

    def test_is_provider_enabled(self):
        config = DataProvidersConfig(
            providers={
                "csv": ProviderEntry(enabled=True),
                "zerodha": ProviderEntry(enabled=False),
            }
        )
        assert config.is_provider_enabled("csv") is True
        assert config.is_provider_enabled("zerodha") is False
        assert config.is_provider_enabled("nonexistent") is False

    def test_list_enabled_providers(self):
        config = DataProvidersConfig(
            providers={
                "csv": ProviderEntry(enabled=True),
                "zerodha": ProviderEntry(enabled=False),
                "upstox": ProviderEntry(enabled=True),
            }
        )
        enabled = config.list_enabled_providers()
        assert "csv" in enabled
        assert "upstox" in enabled
        assert "zerodha" not in enabled

    def test_get_default(self):
        config = DataProvidersConfig(
            default_provider="indian_csv",
            providers={"indian_csv": ProviderEntry()},
        )
        default = config.get_default()
        assert default is not None


class TestEnvOverrides:

    def test_env_overrides_credentials(self):
        config = DataProvidersConfig(
            providers={"zerodha": ProviderEntry()}
        )
        env = {
            "ZERODHA_API_KEY": "env_key",
            "ZERODHA_API_SECRET": "env_secret",
            "ZERODHA_ACCESS_TOKEN": "env_token",
        }
        with mock.patch.dict(os.environ, env):
            config = _apply_env_overrides(config)

        entry = config.get_provider("zerodha")
        assert entry.api_key == "env_key"
        assert entry.api_secret == "env_secret"
        assert entry.access_token == "env_token"

    def test_env_partial_override(self):
        config = DataProvidersConfig(
            providers={"upstox": ProviderEntry(api_key="yaml_key")}
        )
        env = {"UPSTOX_API_SECRET": "env_secret"}
        with mock.patch.dict(os.environ, env):
            config = _apply_env_overrides(config)

        entry = config.get_provider("upstox")
        assert entry.api_key == "yaml_key"  # not overridden
        assert entry.api_secret == "env_secret"  # overridden


class TestLoadProviderConfig:

    def test_load_defaults_when_no_file(self, tmp_path):
        config = load_provider_config(str(tmp_path / "nonexistent.yaml"))
        assert config.default_provider == "csv"

    def test_load_from_yaml(self, tmp_path):
        yaml_content = """\
default_provider: indian_csv
providers:
  csv:
    enabled: true
    data_dir: "data/"
  indian_csv:
    enabled: true
    timezone: "Asia/Kolkata"
  zerodha:
    enabled: false
    api_key: "yaml_key"
"""
        config_file = tmp_path / "providers.yaml"
        config_file.write_text(yaml_content)

        config = load_provider_config(str(config_file))
        assert config.default_provider == "indian_csv"
        assert config.is_provider_enabled("csv") is True
        assert config.is_provider_enabled("zerodha") is False
        assert config.get_provider("zerodha").api_key == "yaml_key"

    def test_load_yaml_with_env_override(self, tmp_path):
        yaml_content = """\
default_provider: csv
providers:
  zerodha:
    enabled: true
    api_key: ""
"""
        config_file = tmp_path / "providers.yaml"
        config_file.write_text(yaml_content)

        env = {"ZERODHA_API_KEY": "from_env"}
        with mock.patch.dict(os.environ, env):
            config = load_provider_config(str(config_file))

        assert config.get_provider("zerodha").api_key == "from_env"
