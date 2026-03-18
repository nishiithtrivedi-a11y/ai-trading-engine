"""
Tests for provider capability extensions and registry derivative methods — Phase 2.
"""
from __future__ import annotations

from datetime import date

import pytest

from src.data.instrument_metadata import InstrumentType, OptionType
from src.data.provider_capabilities import (
    get_derivative_capability_summary,
    get_provider_feature_set,
)
from src.instruments.enums import Exchange
from src.instruments.instrument import Instrument
from src.instruments.registry import InstrumentRegistry


# ---------------------------------------------------------------------------
# Provider capability extension tests
# ---------------------------------------------------------------------------

class TestZerodhaDerivativeCapabilities:
    @pytest.fixture(autouse=True)
    def cap(self):
        self.fs = get_provider_feature_set("zerodha")

    def test_supports_historical_derivatives(self):
        assert self.fs.supports_historical_derivatives is True

    def test_supports_latest_derivatives(self):
        assert self.fs.supports_latest_derivatives is True

    def test_supports_oi(self):
        assert self.fs.supports_oi is True

    def test_supports_market_depth(self):
        assert self.fs.supports_market_depth is True

    def test_instrument_master_available(self):
        assert self.fs.instrument_master_available is True

    def test_supports_derivatives_flag(self):
        assert self.fs.supports_derivatives is True


class TestUpstoxDerivativeCapabilities:
    @pytest.fixture(autouse=True)
    def cap(self):
        self.fs = get_provider_feature_set("upstox")

    def test_supports_historical_derivatives_false(self):
        assert self.fs.supports_historical_derivatives is False

    def test_supports_latest_derivatives_false(self):
        assert self.fs.supports_latest_derivatives is False

    def test_supports_oi_false(self):
        assert self.fs.supports_oi is False

    def test_supports_market_depth_false(self):
        assert self.fs.supports_market_depth is False

    def test_instrument_master_available_false(self):
        assert self.fs.instrument_master_available is False


class TestCsvDerivativeCapabilities:
    @pytest.fixture(autouse=True)
    def cap(self):
        self.fs = get_provider_feature_set("csv")

    def test_supports_historical_derivatives_false(self):
        assert self.fs.supports_historical_derivatives is False

    def test_supports_oi_false(self):
        assert self.fs.supports_oi is False

    def test_supports_market_depth_false(self):
        assert self.fs.supports_market_depth is False

    def test_instrument_master_available_false(self):
        assert self.fs.instrument_master_available is False


class TestIndianCsvDerivativeCapabilities:
    def test_all_derivative_flags_false(self):
        fs = get_provider_feature_set("indian_csv")
        assert fs.supports_historical_derivatives is False
        assert fs.supports_latest_derivatives is False
        assert fs.supports_oi is False
        assert fs.supports_market_depth is False
        assert fs.instrument_master_available is False


# ---------------------------------------------------------------------------
# get_derivative_capability_summary
# ---------------------------------------------------------------------------

class TestGetDerivativeCapabilitySummary:
    def test_returns_dict(self):
        result = get_derivative_capability_summary("zerodha")
        assert isinstance(result, dict)

    def test_dict_has_required_keys(self):
        result = get_derivative_capability_summary("zerodha")
        expected_keys = {
            "provider",
            "supports_derivatives",
            "supports_historical_derivatives",
            "supports_latest_derivatives",
            "supports_oi",
            "supports_market_depth",
            "instrument_master_available",
            "supported_segments",
            "implementation_status",
        }
        assert expected_keys <= set(result.keys())

    def test_zerodha_summary_values(self):
        result = get_derivative_capability_summary("zerodha")
        assert result["provider"] == "zerodha"
        assert result["supports_oi"] is True
        assert result["instrument_master_available"] is True

    def test_upstox_summary_values(self):
        result = get_derivative_capability_summary("upstox")
        assert result["supports_historical_derivatives"] is False
        assert result["supports_oi"] is False

    def test_csv_summary(self):
        result = get_derivative_capability_summary("csv")
        assert result["supports_derivatives"] is False

    def test_supported_segments_is_list(self):
        result = get_derivative_capability_summary("zerodha")
        assert isinstance(result["supported_segments"], list)
        assert "NFO" in result["supported_segments"]

    def test_unknown_provider_raises(self):
        from src.data.provider_capabilities import ProviderCapabilityError
        with pytest.raises(ProviderCapabilityError):
            get_derivative_capability_summary("bogus_provider")


# ---------------------------------------------------------------------------
# InstrumentRegistry — list_by_underlying
# ---------------------------------------------------------------------------

class TestRegistryListByUnderlying:
    @pytest.fixture
    def registry_with_derivatives(self):
        reg = InstrumentRegistry()
        reg.add(Instrument.equity("RELIANCE", exchange=Exchange.NSE))
        reg.add(Instrument.future("NIFTY", date(2026, 4, 30), exchange=Exchange.NFO))
        reg.add(Instrument.future("NIFTY", date(2026, 5, 28), exchange=Exchange.NFO))
        reg.add(Instrument.option("NIFTY", date(2026, 4, 30), 24500.0, OptionType.CALL, exchange=Exchange.NFO))
        reg.add(Instrument.option("NIFTY", date(2026, 4, 30), 24500.0, OptionType.PUT, exchange=Exchange.NFO))
        reg.add(Instrument.future("BANKNIFTY", date(2026, 4, 30), exchange=Exchange.NFO))
        return reg

    def test_list_by_underlying_nifty(self, registry_with_derivatives):
        result = registry_with_derivatives.list_by_underlying("NIFTY")
        assert len(result) == 4  # 2 futures + 2 options

    def test_list_by_underlying_banknifty(self, registry_with_derivatives):
        result = registry_with_derivatives.list_by_underlying("BANKNIFTY")
        assert len(result) == 1

    def test_list_by_underlying_with_exchange_filter(self, registry_with_derivatives):
        result = registry_with_derivatives.list_by_underlying("NIFTY", exchange=Exchange.NFO)
        assert len(result) == 4

    def test_list_by_underlying_empty_when_not_found(self, registry_with_derivatives):
        result = registry_with_derivatives.list_by_underlying("DOESNOTEXIST")
        assert result == []

    def test_list_by_underlying_case_insensitive(self, registry_with_derivatives):
        result = registry_with_derivatives.list_by_underlying("nifty")
        assert len(result) == 4


# ---------------------------------------------------------------------------
# InstrumentRegistry — list_by_expiry
# ---------------------------------------------------------------------------

class TestRegistryListByExpiry:
    @pytest.fixture
    def registry_with_derivatives(self):
        reg = InstrumentRegistry()
        reg.add(Instrument.future("NIFTY", date(2026, 4, 30), exchange=Exchange.NFO))
        reg.add(Instrument.future("NIFTY", date(2026, 5, 28), exchange=Exchange.NFO))
        reg.add(Instrument.option("NIFTY", date(2026, 4, 30), 24500.0, OptionType.CALL, exchange=Exchange.NFO))
        return reg

    def test_list_by_expiry_april(self, registry_with_derivatives):
        result = registry_with_derivatives.list_by_expiry(date(2026, 4, 30))
        assert len(result) == 2  # future + call option

    def test_list_by_expiry_may(self, registry_with_derivatives):
        result = registry_with_derivatives.list_by_expiry(date(2026, 5, 28))
        assert len(result) == 1

    def test_list_by_expiry_no_match(self, registry_with_derivatives):
        result = registry_with_derivatives.list_by_expiry(date(2030, 1, 1))
        assert result == []


# ---------------------------------------------------------------------------
# InstrumentRegistry — list_active_futures
# ---------------------------------------------------------------------------

class TestRegistryListActiveFutures:
    @pytest.fixture
    def registry(self):
        reg = InstrumentRegistry()
        reg.add(Instrument.future("NIFTY", date(2026, 4, 30), exchange=Exchange.NFO))
        reg.add(Instrument.future("NIFTY", date(2026, 5, 28), exchange=Exchange.NFO))
        reg.add(Instrument.future("NIFTY", date(2025, 12, 25), exchange=Exchange.NFO))
        reg.add(Instrument.equity("RELIANCE", exchange=Exchange.NSE))
        return reg

    def test_returns_only_futures(self, registry):
        result = registry.list_active_futures(as_of=date(2026, 1, 1))
        assert all(i.instrument_type == InstrumentType.FUTURE for i in result)

    def test_filters_expired(self, registry):
        result = registry.list_active_futures(as_of=date(2026, 1, 1))
        # Dec 2025 expiry is before 2026-01-01, should be excluded
        assert all(i.expiry >= date(2026, 1, 1) for i in result)
        assert len(result) == 2

    def test_sorted_by_expiry(self, registry):
        result = registry.list_active_futures(as_of=date(2026, 1, 1))
        expiries = [i.expiry for i in result]
        assert expiries == sorted(expiries)

    def test_all_expired_returns_empty(self, registry):
        result = registry.list_active_futures(as_of=date(2030, 1, 1))
        assert result == []


# ---------------------------------------------------------------------------
# InstrumentRegistry — list_option_chain
# ---------------------------------------------------------------------------

class TestRegistryListOptionChain:
    @pytest.fixture
    def registry(self):
        reg = InstrumentRegistry()
        exp = date(2026, 4, 30)
        reg.add(Instrument.option("NIFTY", exp, 24000.0, OptionType.CALL, exchange=Exchange.NFO))
        reg.add(Instrument.option("NIFTY", exp, 24500.0, OptionType.CALL, exchange=Exchange.NFO))
        reg.add(Instrument.option("NIFTY", exp, 24000.0, OptionType.PUT, exchange=Exchange.NFO))
        reg.add(Instrument.option("NIFTY", exp, 24500.0, OptionType.PUT, exchange=Exchange.NFO))
        # Different expiry
        reg.add(Instrument.option("NIFTY", date(2026, 5, 28), 24000.0, OptionType.CALL, exchange=Exchange.NFO))
        # Different underlying
        reg.add(Instrument.option("BANKNIFTY", exp, 48000.0, OptionType.CALL, exchange=Exchange.NFO))
        return reg

    def test_option_chain_count(self, registry):
        result = registry.list_option_chain("NIFTY", date(2026, 4, 30))
        assert len(result) == 4

    def test_option_chain_sorted_by_strike(self, registry):
        result = registry.list_option_chain("NIFTY", date(2026, 4, 30))
        strikes = [i.strike for i in result]
        assert strikes == sorted(strikes)

    def test_option_chain_excludes_other_expiry(self, registry):
        result = registry.list_option_chain("NIFTY", date(2026, 4, 30))
        assert all(i.expiry == date(2026, 4, 30) for i in result)

    def test_option_chain_excludes_other_underlying(self, registry):
        result = registry.list_option_chain("NIFTY", date(2026, 4, 30))
        assert all(i.symbol == "NIFTY" for i in result)

    def test_option_chain_with_exchange_filter(self, registry):
        result = registry.list_option_chain("NIFTY", date(2026, 4, 30), exchange=Exchange.NFO)
        assert len(result) == 4

    def test_option_chain_empty_when_no_match(self, registry):
        result = registry.list_option_chain("NIFTY", date(2030, 1, 1))
        assert result == []
