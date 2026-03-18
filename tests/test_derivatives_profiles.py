"""Tests for derivative analysis profiles."""
from __future__ import annotations

import pytest

from src.analysis.registry import AnalysisRegistry
from src.config.analysis_profiles import AnalysisProfileLoader


def _load_profile(name: str):
    loader = AnalysisProfileLoader()
    return loader.get(name)


def _apply_profile(profile_name: str) -> AnalysisRegistry:
    loader = AnalysisProfileLoader()
    profile = loader.get(profile_name)
    registry = AnalysisRegistry.create_default()
    loader.apply_to_registry(profile, registry)
    return registry


class TestNewDerivativeProfiles:
    def test_index_futures_profile_exists(self):
        loader = AnalysisProfileLoader()
        assert "index_futures" in loader.list_profiles()

    def test_stock_futures_profile_exists(self):
        loader = AnalysisProfileLoader()
        assert "stock_futures" in loader.list_profiles()

    def test_equity_options_profile_exists(self):
        loader = AnalysisProfileLoader()
        assert "equity_options" in loader.list_profiles()

    def test_inr_currency_derivatives_profile_exists(self):
        loader = AnalysisProfileLoader()
        assert "inr_currency_derivatives" in loader.list_profiles()

    def test_index_futures_enables_technical(self):
        r = _apply_profile("index_futures")
        assert r.is_enabled("technical")

    def test_index_futures_enables_quant(self):
        r = _apply_profile("index_futures")
        assert r.is_enabled("quant")

    def test_index_futures_enables_futures(self):
        r = _apply_profile("index_futures")
        assert r.is_enabled("futures")

    def test_index_futures_does_not_enable_options(self):
        r = _apply_profile("index_futures")
        assert not r.is_enabled("options")

    def test_stock_futures_enables_futures(self):
        r = _apply_profile("stock_futures")
        assert r.is_enabled("futures")

    def test_stock_futures_enables_technical_and_quant(self):
        r = _apply_profile("stock_futures")
        assert r.is_enabled("technical")
        assert r.is_enabled("quant")

    def test_equity_options_enables_options(self):
        r = _apply_profile("equity_options")
        assert r.is_enabled("options")

    def test_equity_options_enables_technical(self):
        r = _apply_profile("equity_options")
        assert r.is_enabled("technical")

    def test_equity_options_enables_quant(self):
        r = _apply_profile("equity_options")
        assert r.is_enabled("quant")

    def test_equity_options_does_not_enable_futures(self):
        r = _apply_profile("equity_options")
        assert not r.is_enabled("futures")

    def test_commodity_futures_has_futures_and_commodities(self):
        r = _apply_profile("commodity_futures")
        assert r.is_enabled("futures")
        assert r.is_enabled("commodities")

    def test_inr_currency_derivatives_enables_futures_and_forex(self):
        r = _apply_profile("inr_currency_derivatives")
        assert r.is_enabled("futures")
        assert r.is_enabled("forex")

    def test_inr_currency_derivatives_enables_technical_and_quant(self):
        r = _apply_profile("inr_currency_derivatives")
        assert r.is_enabled("technical")
        assert r.is_enabled("quant")


class TestExistingProfilesUnchanged:
    def test_default_profile_exists(self):
        loader = AnalysisProfileLoader()
        assert "default" in loader.list_profiles()

    def test_default_profile_enables_technical_and_quant(self):
        r = _apply_profile("default")
        assert r.is_enabled("technical")
        assert r.is_enabled("quant")

    def test_default_profile_only_enables_technical_and_quant(self):
        r = _apply_profile("default")
        enabled = {m.name for m in r.enabled_modules()}
        assert enabled == {"technical", "quant"}

    def test_index_options_profile_exists(self):
        loader = AnalysisProfileLoader()
        assert "index_options" in loader.list_profiles()

    def test_index_options_enables_options(self):
        r = _apply_profile("index_options")
        assert r.is_enabled("options")

    def test_index_options_enables_sentiment(self):
        r = _apply_profile("index_options")
        assert r.is_enabled("sentiment")

    def test_commodity_futures_profile_exists(self):
        loader = AnalysisProfileLoader()
        assert "commodity_futures" in loader.list_profiles()

    def test_swing_equity_profile_exists(self):
        loader = AnalysisProfileLoader()
        assert "swing_equity" in loader.list_profiles()


class TestProfileSwitching:
    def test_apply_derivative_then_default_disables_futures(self):
        loader = AnalysisProfileLoader()

        # First apply index_futures profile
        registry = AnalysisRegistry.create_default()
        loader.apply_to_registry(loader.get("index_futures"), registry)
        assert registry.is_enabled("futures")

        # Then apply default — futures should be disabled again
        loader.apply_to_registry(loader.get("default"), registry)
        assert not registry.is_enabled("futures")

    def test_apply_equity_options_then_default_disables_options(self):
        loader = AnalysisProfileLoader()

        registry = AnalysisRegistry.create_default()
        loader.apply_to_registry(loader.get("equity_options"), registry)
        assert registry.is_enabled("options")

        loader.apply_to_registry(loader.get("default"), registry)
        assert not registry.is_enabled("options")

    def test_futures_module_enabled_after_index_futures_profile(self):
        """Futures module should appear in enabled_modules() after applying profile."""
        r = _apply_profile("index_futures")
        enabled_names = {m.name for m in r.enabled_modules()}
        assert "futures" in enabled_names
