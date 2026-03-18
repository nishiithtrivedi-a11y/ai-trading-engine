from __future__ import annotations

from src.data.provider_capabilities import (
    AnalysisFamily,
    get_analysis_provider_feature_set,
    list_analysis_provider_feature_sets,
    validate_analysis_provider_family,
)
from src.data.provider_config import (
    AnalysisProvidersConfig,
    DataProvidersConfig,
    ProviderEntry,
)
from src.data.provider_factory import ProviderFactory
from src.data.provider_router import AnalysisProviderRouter, AnalysisProviderRoutingPolicy


def test_analysis_provider_registry_contains_expected_choices() -> None:
    registry = list_analysis_provider_feature_sets()
    assert {"none", "alphavantage", "finnhub", "fmp", "eodhd", "derived"}.issubset(
        set(registry.keys())
    )


def test_validate_analysis_provider_family_supports_fundamentals() -> None:
    fs = validate_analysis_provider_family("fmp", AnalysisFamily.FUNDAMENTALS)
    assert fs.supports_fundamentals is True


def test_validate_analysis_provider_family_rejects_none() -> None:
    try:
        validate_analysis_provider_family("none", AnalysisFamily.MACRO)
    except Exception as exc:  # noqa: BLE001
        assert "does not support family" in str(exc)
    else:
        raise AssertionError("Expected provider-family validation to fail for none/macro")


def test_analysis_provider_router_selects_fallback_when_needed() -> None:
    policy = AnalysisProviderRoutingPolicy(
        fundamentals_provider="none",
        macro_provider="none",
        sentiment_provider="none",
        intermarket_provider="none",
        fallback_order=["fmp", "none"],
    )
    router = AnalysisProviderRouter(policy)
    assert router.select_for_family("fundamentals") == "fmp"
    # Intermarket should still be able to select a derived path.
    assert router.select_for_family("intermarket") in {"derived", "fmp"}


def test_provider_factory_analysis_capability_report_from_config() -> None:
    cfg = DataProvidersConfig(
        default_provider="csv",
        providers={"csv": ProviderEntry(enabled=True)},
        analysis_providers=AnalysisProvidersConfig(
            fundamentals_provider="fmp",
            macro_provider="alphavantage",
            sentiment_provider="finnhub",
            intermarket_provider="derived",
            allow_derived_sentiment_fallback=True,
        ),
    )
    factory = ProviderFactory(cfg)
    report = factory.analysis_capability_report()

    assert report["configured"]["fundamentals_provider"] == "fmp"
    assert report["fundamentals"]["provider"] == "fmp"
    assert report["macro"]["provider"] == "alphavantage"
    assert report["sentiment"]["provider"] == "finnhub"
    assert report["intermarket"]["provider"] in {"derived", "fmp", "alphavantage", "finnhub", "eodhd"}
    assert report["allow_derived_sentiment_fallback"] is True


def test_get_analysis_provider_feature_set_truthfulness() -> None:
    fs = get_analysis_provider_feature_set("eodhd")
    assert fs.supports_macro is True
    assert fs.supports_news is True
