"""Tests for activated derivative analysis modules."""
from __future__ import annotations

import pytest
import pandas as pd
import numpy as np
from datetime import date

from src.analysis.derivatives.futures.module import FuturesAnalysisModule
from src.analysis.derivatives.options.module import OptionsAnalysisModule
from src.analysis.derivatives.commodities.module import CommoditiesAnalysisModule
from src.analysis.derivatives.forex.module import ForexAnalysisModule
from src.analysis.registry import AnalysisRegistry
from src.analysis.derivatives.futures.intelligence import FuturesContractInfo
from src.analysis.derivatives.options.chain import OptionChain, OptionStrike
from src.analysis.derivatives.options.analytics import ChainAnalytics


# ---------------------------------------------------------------------------
# FuturesAnalysisModule tests
# ---------------------------------------------------------------------------

class TestFuturesAnalysisModule:
    def _module(self) -> FuturesAnalysisModule:
        return FuturesAnalysisModule()

    def test_is_enabled_returns_true(self):
        m = self._module()
        assert m.is_enabled() is True

    def test_version_is_1_0_0(self):
        m = self._module()
        assert m.version == "1.0.0"

    def test_health_check_status_ok(self):
        m = self._module()
        hc = m.health_check()
        assert hc["status"] == "ok"

    def test_health_check_module_name(self):
        m = self._module()
        hc = m.health_check()
        assert hc["module"] == "futures"

    def test_build_features_empty_context_returns_dict(self):
        m = self._module()
        result = m.build_features(pd.DataFrame(), {})
        assert isinstance(result, dict)

    def test_build_features_with_contract_info(self):
        m = self._module()
        ci = FuturesContractInfo(
            canonical="NFO:NIFTY-2026-04-30-FUT",
            underlying="NIFTY",
            exchange="NFO",
            expiry=date(2026, 4, 30),
            days_to_expiry=43,
            contract_position="front",
        )
        result = m.build_features(pd.DataFrame(), {"contract_info": ci})
        assert "days_to_expiry" in result
        assert result["days_to_expiry"] == pytest.approx(43.0)
        assert "roll_imminent" in result
        assert result["roll_imminent"] == 0.0  # 43 > 5

    def test_build_features_roll_imminent_when_dte_low(self):
        m = self._module()
        ci = FuturesContractInfo(
            canonical="NFO:NIFTY-2026-03-20-FUT",
            underlying="NIFTY",
            exchange="NFO",
            expiry=date(2026, 3, 20),
            days_to_expiry=2,
            contract_position="front",
        )
        result = m.build_features(pd.DataFrame(), {"contract_info": ci})
        assert result["roll_imminent"] == 1.0

    def test_build_features_basis_calculation(self):
        m = self._module()
        result = m.build_features(
            pd.DataFrame(), {"spot_price": 22000.0, "futures_price": 22100.0}
        )
        assert "basis" in result
        assert result["basis"] == pytest.approx(100.0)
        assert "basis_pct" in result
        assert result["contango"] == pytest.approx(1.0)
        assert result["backwardation"] == pytest.approx(0.0)

    def test_build_features_backwardation(self):
        m = self._module()
        result = m.build_features(
            pd.DataFrame(), {"spot_price": 22100.0, "futures_price": 22000.0}
        )
        assert result["contango"] == pytest.approx(0.0)
        assert result["backwardation"] == pytest.approx(1.0)

    def test_build_features_oi_in_context(self):
        m = self._module()
        result = m.build_features(pd.DataFrame(), {"oi": 500000})
        assert "open_interest" in result
        assert result["open_interest"] == pytest.approx(500000.0)

    def test_build_features_price_change_from_ohlcv(self):
        m = self._module()
        df = pd.DataFrame({"close": [22000.0, 22100.0]})
        result = m.build_features(df, {})
        assert "price_change_pct" in result
        assert result["price_change_pct"] == pytest.approx(100 / 22000 * 100)

    def test_supports_future_instrument_type(self):
        m = self._module()
        assert m.supports("future", "DAILY") is True

    def test_supports_futures_string(self):
        m = self._module()
        assert m.supports("futures", "DAILY") is True

    def test_supports_commodity(self):
        m = self._module()
        assert m.supports("commodity", "DAILY") is True

    def test_does_not_support_equity(self):
        m = self._module()
        assert m.supports("equity", "DAILY") is False


# ---------------------------------------------------------------------------
# OptionsAnalysisModule tests
# ---------------------------------------------------------------------------

class TestOptionsAnalysisModule:
    def _module(self) -> OptionsAnalysisModule:
        return OptionsAnalysisModule()

    def test_is_enabled_returns_true(self):
        assert self._module().is_enabled() is True

    def test_health_check_status_ok(self):
        hc = self._module().health_check()
        assert hc["status"] == "ok"

    def test_health_check_module_name(self):
        hc = self._module().health_check()
        assert hc["module"] == "options"

    def test_build_features_empty_context_returns_dict(self):
        result = self._module().build_features(pd.DataFrame(), {})
        assert isinstance(result, dict)

    def test_build_features_with_chain_analytics(self):
        analytics = ChainAnalytics(
            underlying="NIFTY",
            expiry="2026-04-30",
            spot_price=22000.0,
            atm_strike=22000.0,
            pcr_overall=1.2,
            max_pain=21500.0,
            iv_skew=0.02,
            call_oi_total=600000,
            put_oi_total=720000,
            highest_oi_call_strike=22500.0,
            highest_oi_put_strike=21500.0,
            call_resistance=22500.0,
            put_support=21500.0,
            chain_breadth=5,
        )
        m = self._module()
        result = m.build_features(pd.DataFrame(), {"chain_analytics": analytics})
        assert "pcr_overall" in result
        assert result["pcr_overall"] == pytest.approx(1.2)
        assert "call_oi_total" in result
        assert "put_oi_total" in result
        assert "atm_strike" in result
        assert "max_pain" in result
        assert result["max_pain"] == pytest.approx(21500.0)
        assert "call_resistance" in result
        assert "put_support" in result

    def test_build_features_with_option_chain_fallback(self):
        chain = OptionChain(
            underlying="NIFTY",
            expiry=date(2026, 4, 30),
            spot_price=22000.0,
        )
        chain.strikes = [
            OptionStrike(strike=22000.0, ce_oi=100000, pe_oi=120000),
            OptionStrike(strike=22500.0, ce_oi=150000, pe_oi=80000),
        ]
        m = self._module()
        result = m.build_features(pd.DataFrame(), {"option_chain": chain})
        assert "pcr_overall" in result
        assert "call_oi_total" in result
        assert "atm_strike" in result

    def test_build_features_with_days_to_expiry(self):
        m = self._module()
        result = m.build_features(pd.DataFrame(), {"days_to_expiry": 7.0})
        assert "days_to_expiry" in result
        assert result["days_to_expiry"] == pytest.approx(7.0)

    def test_supports_option(self):
        assert self._module().supports("option", "DAILY") is True

    def test_supports_options_plural(self):
        assert self._module().supports("options", "DAILY") is True

    def test_does_not_support_future(self):
        assert self._module().supports("future", "DAILY") is False


# ---------------------------------------------------------------------------
# CommoditiesAnalysisModule tests
# ---------------------------------------------------------------------------

class TestCommoditiesAnalysisModule:
    def _module(self) -> CommoditiesAnalysisModule:
        return CommoditiesAnalysisModule()

    def test_is_enabled_returns_true(self):
        assert self._module().is_enabled() is True

    def test_health_check_status_ok(self):
        hc = self._module().health_check()
        assert hc["status"] == "ok"

    def test_build_features_includes_asset_class_commodity(self):
        m = self._module()
        result = m.build_features(pd.DataFrame(), {})
        assert result.get("asset_class") == "commodity"

    def test_build_features_delegates_to_futures_basis(self):
        m = self._module()
        result = m.build_features(
            pd.DataFrame(), {"spot_price": 5000.0, "futures_price": 5100.0}
        )
        assert "basis" in result
        assert result["basis"] == pytest.approx(100.0)

    def test_supports_commodity(self):
        assert self._module().supports("commodity", "DAILY") is True

    def test_supports_future(self):
        assert self._module().supports("future", "DAILY") is True

    def test_module_name(self):
        assert self._module().name == "commodities"

    def test_version(self):
        assert self._module().version == "1.0.0"


# ---------------------------------------------------------------------------
# ForexAnalysisModule tests
# ---------------------------------------------------------------------------

class TestForexAnalysisModule:
    def _module(self) -> ForexAnalysisModule:
        return ForexAnalysisModule()

    def test_is_enabled_returns_true(self):
        assert self._module().is_enabled() is True

    def test_health_check_status_ok(self):
        hc = self._module().health_check()
        assert hc["status"] == "ok"

    def test_build_features_includes_asset_class_currency(self):
        result = self._module().build_features(pd.DataFrame(), {})
        assert result.get("asset_class") == "currency"

    def test_build_features_includes_pair_from_context(self):
        result = self._module().build_features(pd.DataFrame(), {"underlying": "USDINR"})
        assert result.get("pair") == "USDINR"

    def test_build_features_default_pair_usdinr(self):
        result = self._module().build_features(pd.DataFrame(), {})
        assert result.get("pair") == "USDINR"

    def test_build_features_delegates_basis(self):
        result = self._module().build_features(
            pd.DataFrame(), {"spot_price": 84.5, "futures_price": 84.8}
        )
        assert "basis" in result
        assert result["basis"] == pytest.approx(0.3, abs=0.01)

    def test_supports_forex(self):
        assert self._module().supports("forex", "DAILY") is True

    def test_supports_currency(self):
        assert self._module().supports("currency", "DAILY") is True

    def test_module_name(self):
        assert self._module().name == "forex"

    def test_version(self):
        assert self._module().version == "1.0.0"


# ---------------------------------------------------------------------------
# Registry integration tests
# ---------------------------------------------------------------------------

class TestRegistryIntegration:
    def test_create_default_still_disables_futures(self):
        """Futures module is_enabled()=True but registry.create_default() disables it."""
        r = AnalysisRegistry.create_default()
        assert r.is_enabled("futures") is False

    def test_create_default_still_disables_options(self):
        r = AnalysisRegistry.create_default()
        assert r.is_enabled("options") is False

    def test_create_default_still_disables_commodities(self):
        r = AnalysisRegistry.create_default()
        assert r.is_enabled("commodities") is False

    def test_create_default_still_disables_forex(self):
        r = AnalysisRegistry.create_default()
        assert r.is_enabled("forex") is False

    def test_create_default_enabled_only_technical_and_quant(self):
        r = AnalysisRegistry.create_default()
        enabled = {m.name for m in r.enabled_modules()}
        assert enabled == {"technical", "quant"}

    def test_futures_module_in_all_modules(self):
        r = AnalysisRegistry.create_default()
        all_names = {m.name for m in r.all_modules()}
        assert "futures" in all_names

    def test_options_module_in_all_modules(self):
        r = AnalysisRegistry.create_default()
        all_names = {m.name for m in r.all_modules()}
        assert "options" in all_names

    def test_enable_futures_manually(self):
        r = AnalysisRegistry.create_default()
        r.enable("futures")
        assert r.is_enabled("futures") is True

    def test_enable_options_manually(self):
        r = AnalysisRegistry.create_default()
        r.enable("options")
        assert r.is_enabled("options") is True
