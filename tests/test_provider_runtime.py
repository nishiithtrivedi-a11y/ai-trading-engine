from __future__ import annotations

from src.data.provider_config import DataProvidersConfig, ProviderEntry
from src.data.provider_runtime import (
    ProviderRuntimeState,
    can_create_provider,
    get_provider_readiness_report,
    list_all_provider_reports,
    resolve_provider_credentials,
)


def _clear_zerodha_env(monkeypatch) -> None:
    for key in ("ZERODHA_API_KEY", "ZERODHA_API_SECRET", "ZERODHA_ACCESS_TOKEN"):
        monkeypatch.delenv(key, raising=False)


def test_readiness_reports_disabled_provider(monkeypatch) -> None:
    _clear_zerodha_env(monkeypatch)
    config = DataProvidersConfig(
        default_provider="zerodha",
        providers={
            "zerodha": ProviderEntry(
                enabled=False,
                api_key="key",
                api_secret="secret",
                access_token="token",
            )
        },
    )
    report = get_provider_readiness_report("zerodha", config=config, require_enabled=True)
    assert report.state == ProviderRuntimeState.DISABLED
    assert report.can_instantiate is False


def test_readiness_reports_missing_credentials(monkeypatch) -> None:
    _clear_zerodha_env(monkeypatch)
    config = DataProvidersConfig(
        default_provider="zerodha",
        providers={"zerodha": ProviderEntry(enabled=True)},
    )
    report = get_provider_readiness_report("zerodha", config=config, require_enabled=True)
    assert report.state == ProviderRuntimeState.MISSING_SECRETS
    assert report.can_instantiate is False


def test_resolve_dhan_credentials_supports_client_id_alias(monkeypatch) -> None:
    monkeypatch.delenv("DHAN_API_KEY", raising=False)
    monkeypatch.setenv("DHAN_CLIENT_ID", "client_alias_value")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "token_value")
    config = DataProvidersConfig(
        default_provider="dhan",
        providers={"dhan": ProviderEntry(enabled=True)},
    )
    resolved = resolve_provider_credentials("dhan", config=config)
    assert resolved.is_fully_configured is True
    assert resolved.values["CLIENT_ID"] == "client_alias_value"
    assert resolved.values["ACCESS_TOKEN"] == "token_value"


def test_can_create_provider_respects_workflow_capability() -> None:
    config = DataProvidersConfig(
        default_provider="csv",
        providers={"csv": ProviderEntry(enabled=True)},
    )
    can_create = can_create_provider(
        "csv",
        config=config,
        require_enabled=True,
        require_live_quotes=True,
        timeframe="1D",
    )
    assert can_create is False


def test_list_all_provider_reports_includes_configured_entries() -> None:
    config = DataProvidersConfig(
        default_provider="csv",
        providers={
            "csv": ProviderEntry(enabled=True),
            "zerodha": ProviderEntry(enabled=True),
        },
    )
    reports = list_all_provider_reports(config=config, require_enabled=False)
    names = {report.provider_name for report in reports}
    assert "csv" in names
    assert "zerodha" in names

