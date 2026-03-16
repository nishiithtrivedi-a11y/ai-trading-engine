from __future__ import annotations

import pytest

from src.data.instrument_metadata import InstrumentType
from src.data.provider_capabilities import (
    ProviderCapabilityError,
    ProviderFeature,
    get_provider_feature_set,
    list_provider_feature_sets,
    validate_provider_feature,
    validate_provider_workflow,
)


def test_provider_capability_registry_has_expected_providers() -> None:
    registry = list_provider_feature_sets()
    assert set(registry.keys()) >= {"csv", "indian_csv", "zerodha", "upstox"}


def test_get_provider_feature_set_unknown_provider_raises() -> None:
    with pytest.raises(ProviderCapabilityError, match="Unknown provider"):
        get_provider_feature_set("unknown_provider")


def test_validate_provider_feature_supports_historical_for_zerodha() -> None:
    validate_provider_feature("zerodha", ProviderFeature.HISTORICAL_DATA)


def test_validate_provider_workflow_rejects_upstox_historical() -> None:
    with pytest.raises(ProviderCapabilityError, match="historical_data"):
        validate_provider_workflow(
            "upstox",
            require_historical_data=True,
            timeframe="1D",
            instrument_type=InstrumentType.EQUITY,
        )


def test_validate_provider_workflow_rejects_csv_live_quotes() -> None:
    with pytest.raises(ProviderCapabilityError, match="live_quotes"):
        validate_provider_workflow(
            "csv",
            require_live_quotes=True,
            timeframe="1D",
            instrument_type=InstrumentType.EQUITY,
        )


def test_validate_provider_workflow_rejects_unsupported_intraday() -> None:
    with pytest.raises(ProviderCapabilityError, match="intraday_bars"):
        validate_provider_workflow("upstox", timeframe="5m")


def test_validate_provider_workflow_rejects_unsupported_instrument_type() -> None:
    with pytest.raises(ProviderCapabilityError, match="instrument_type"):
        validate_provider_workflow(
            "csv",
            require_historical_data=True,
            timeframe="1D",
            instrument_type=InstrumentType.FUTURE,
        )

