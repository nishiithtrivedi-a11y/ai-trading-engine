"""
Tests for the Analysis Profiles system — profile loading, apply_to_registry,
list_profiles, and AnalysisProfileError.
"""
from __future__ import annotations

import pytest

from src.analysis.registry import AnalysisRegistry
from src.config.analysis_profiles import (
    AnalysisProfile,
    AnalysisProfileError,
    AnalysisProfileLoader,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _loader() -> AnalysisProfileLoader:
    return AnalysisProfileLoader()


def _default_registry() -> AnalysisRegistry:
    return AnalysisRegistry.create_default()


# ---------------------------------------------------------------------------
# Profile loading
# ---------------------------------------------------------------------------

class TestProfileLoading:
    def test_load_returns_dict(self):
        result = _loader().load()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_expected_profile_names_present(self):
        loader = _loader()
        profiles = loader.list_profiles()
        expected = {
            "default", "intraday_equity", "swing_equity", "positional_equity",
            "index_options", "commodity_futures", "forex_futures", "macro_swing", "full",
        }
        assert expected.issubset(set(profiles))

    def test_list_profiles_returns_list_of_strings(self):
        names = _loader().list_profiles()
        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)

    def test_get_default_profile_returns_analysis_profile(self):
        p = _loader().get("default")
        assert isinstance(p, AnalysisProfile)

    def test_default_profile_enables_technical_and_quant(self):
        p = _loader().get("default")
        assert "technical" in p.enabled
        assert "quant" in p.enabled

    def test_full_profile_enables_all_known_modules(self):
        p = _loader().get("full")
        expected = {
            "technical", "quant", "fundamental", "macro", "sentiment",
            "intermarket", "futures", "options", "commodities", "forex", "crypto",
        }
        assert expected.issubset(set(p.enabled))

    def test_get_missing_profile_raises_analysis_profile_error(self):
        with pytest.raises(AnalysisProfileError):
            _loader().get("nonexistent_profile")

    def test_analysis_profile_error_is_exception(self):
        assert issubclass(AnalysisProfileError, Exception)

    def test_profile_has_name_attribute(self):
        p = _loader().get("default")
        assert p.name == "default"

    def test_profile_has_enabled_list(self):
        p = _loader().get("default")
        assert isinstance(p.enabled, list)

    def test_reload_returns_fresh_dict(self):
        loader = _loader()
        first = loader.load()
        second = loader.reload()
        assert set(first.keys()) == set(second.keys())

    def test_index_options_profile(self):
        p = _loader().get("index_options")
        assert "options" in p.enabled
        assert "technical" in p.enabled

    def test_macro_swing_profile(self):
        p = _loader().get("macro_swing")
        assert "macro" in p.enabled
        assert "intermarket" in p.enabled

    def test_commodity_futures_profile(self):
        p = _loader().get("commodity_futures")
        assert "commodities" in p.enabled

    def test_forex_futures_profile(self):
        p = _loader().get("forex_futures")
        assert "forex" in p.enabled


# ---------------------------------------------------------------------------
# apply_to_registry
# ---------------------------------------------------------------------------

class TestApplyToRegistry:
    def test_apply_default_profile_enables_technical_quant(self):
        loader = _loader()
        registry = _default_registry()
        profile = loader.get("default")
        loader.apply_to_registry(profile, registry)
        assert registry.is_enabled("technical")
        assert registry.is_enabled("quant")

    def test_apply_default_profile_disables_stubs(self):
        loader = _loader()
        registry = _default_registry()
        # Re-enable fundamental first to prove it gets disabled
        registry.enable("fundamental")
        profile = loader.get("default")
        loader.apply_to_registry(profile, registry)
        assert not registry.is_enabled("fundamental")

    def test_apply_full_profile_enables_all(self):
        loader = _loader()
        registry = _default_registry()
        profile = loader.get("full")
        loader.apply_to_registry(profile, registry)
        for name in ["technical", "quant", "fundamental", "macro", "sentiment",
                     "intermarket", "futures", "options", "commodities", "forex", "crypto"]:
            assert registry.is_enabled(name), f"Expected {name!r} to be enabled under 'full'"

    def test_apply_profile_disables_all_not_listed(self):
        loader = _loader()
        registry = _default_registry()
        profile = loader.get("index_options")
        loader.apply_to_registry(profile, registry)
        enabled = {m.name for m in registry.enabled_modules()}
        # All enabled modules must be in the profile's list
        assert enabled.issubset(set(profile.enabled))

    def test_apply_profile_by_name_returns_profile(self):
        loader = _loader()
        registry = _default_registry()
        p = loader.apply_profile_by_name("default", registry)
        assert isinstance(p, AnalysisProfile)
        assert p.name == "default"

    def test_apply_profile_by_name_missing_raises(self):
        loader = _loader()
        registry = _default_registry()
        with pytest.raises(AnalysisProfileError):
            loader.apply_profile_by_name("no_such_profile", registry)

    def test_apply_profile_enables_only_listed_modules(self):
        loader = _loader()
        registry = _default_registry()
        loader.apply_profile_by_name("index_options", registry)
        enabled = {m.name for m in registry.enabled_modules()}
        assert "options" in enabled
        assert "technical" in enabled
        # Modules not in the profile should be disabled
        p = loader.get("index_options")
        not_listed = {m.name for m in registry.all_modules()} - set(p.enabled)
        for name in not_listed:
            assert not registry.is_enabled(name), (
                f"Expected {name!r} to be disabled for profile 'index_options'"
            )

    def test_applying_default_twice_is_idempotent(self):
        loader = _loader()
        registry = _default_registry()
        loader.apply_profile_by_name("default", registry)
        loader.apply_profile_by_name("default", registry)
        assert registry.is_enabled("technical")
        assert registry.is_enabled("quant")
        assert not registry.is_enabled("fundamental")

    def test_switching_profiles_updates_enabled_set(self):
        loader = _loader()
        registry = _default_registry()
        # Start with default (technical + quant)
        loader.apply_profile_by_name("default", registry)
        assert not registry.is_enabled("macro")
        # Switch to macro_swing
        loader.apply_profile_by_name("macro_swing", registry)
        assert registry.is_enabled("macro")
        assert registry.is_enabled("intermarket")


# ---------------------------------------------------------------------------
# AnalysisProfile dataclass
# ---------------------------------------------------------------------------

class TestAnalysisProfileDataclass:
    def test_profile_construction(self):
        p = AnalysisProfile(name="test_profile", enabled=["technical"])
        assert p.name == "test_profile"
        assert p.enabled == ["technical"]

    def test_profile_default_enabled_is_empty(self):
        p = AnalysisProfile(name="empty")
        assert p.enabled == []

    def test_profile_description_default(self):
        p = AnalysisProfile(name="x")
        assert isinstance(p.description, str)
