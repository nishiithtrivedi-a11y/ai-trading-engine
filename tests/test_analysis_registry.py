"""
Tests for the AnalysisRegistry — registration, enable/disable, resolution,
health_check, and create_default().
"""
from __future__ import annotations

import pytest

from src.analysis.base import BaseAnalysisModule
from src.analysis.registry import AnalysisRegistry, AnalysisRegistryError


# ---------------------------------------------------------------------------
# Minimal concrete module for testing
# ---------------------------------------------------------------------------

class _Module(BaseAnalysisModule):
    def __init__(self, name: str, *, enabled: bool = True):
        self._name = name
        self._enabled_flag = enabled

    @property
    def name(self) -> str:  # type: ignore[override]
        return self._name

    def is_enabled(self, config=None) -> bool:
        return self._enabled_flag

    def build_features(self, data, context):
        return {"dummy": 1.0}

    def health_check(self):
        return {"status": "ok", "module": self.name, "version": self.version}


def _reg(*names: str) -> AnalysisRegistry:
    """Create a fresh registry pre-populated with the given module names."""
    r = AnalysisRegistry()
    for n in names:
        r.register(_Module(n))
    return r


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_register_new_module_appears_in_all(self):
        r = _reg("alpha")
        assert any(m.name == "alpha" for m in r.all_modules())

    def test_register_duplicate_raises_without_replace(self):
        r = _reg("alpha")
        with pytest.raises(ValueError, match="already registered"):
            r.register(_Module("alpha"))

    def test_register_duplicate_succeeds_with_replace(self):
        r = _reg("alpha")
        r.register(_Module("alpha"), replace=True)
        assert len([m for m in r.all_modules() if m.name == "alpha"]) == 1

    def test_register_multiple_modules(self):
        r = _reg("a", "b", "c")
        names = {m.name for m in r.all_modules()}
        assert {"a", "b", "c"} == names

    def test_unregister_removes_module(self):
        r = _reg("a", "b")
        r.unregister("a")
        assert not any(m.name == "a" for m in r.all_modules())

    def test_unregister_nonexistent_is_noop(self):
        # unregister() on a name that was never registered is a no-op (no raise)
        r = AnalysisRegistry()
        r.unregister("ghost")  # must not raise

    def test_get_returns_module(self):
        r = _reg("alpha")
        m = r.get("alpha")
        assert m is not None and m.name == "alpha"

    def test_get_missing_returns_none(self):
        r = AnalysisRegistry()
        assert r.get("does_not_exist") is None


# ---------------------------------------------------------------------------
# Enable / Disable
# ---------------------------------------------------------------------------

class TestEnableDisable:
    def test_freshly_registered_module_is_enabled(self):
        r = _reg("alpha")
        assert r.is_enabled("alpha") is True

    def test_disable_removes_from_enabled(self):
        r = _reg("alpha")
        r.disable("alpha")
        assert r.is_enabled("alpha") is False
        assert not any(m.name == "alpha" for m in r.enabled_modules())

    def test_enable_after_disable(self):
        r = _reg("alpha")
        r.disable("alpha")
        r.enable("alpha")
        assert r.is_enabled("alpha") is True
        assert any(m.name == "alpha" for m in r.enabled_modules())

    def test_disable_nonexistent_raises(self):
        r = AnalysisRegistry()
        with pytest.raises(AnalysisRegistryError):
            r.disable("ghost")

    def test_enable_nonexistent_raises(self):
        r = AnalysisRegistry()
        with pytest.raises(AnalysisRegistryError):
            r.enable("ghost")

    def test_enabled_modules_excludes_disabled(self):
        r = _reg("a", "b", "c")
        r.disable("b")
        enabled = {m.name for m in r.enabled_modules()}
        assert "b" not in enabled
        assert {"a", "c"}.issubset(enabled)

    def test_all_modules_includes_disabled(self):
        r = _reg("a", "b")
        r.disable("a")
        all_names = {m.name for m in r.all_modules()}
        assert "a" in all_names

    def test_is_enabled_false_for_disabled(self):
        r = _reg("a")
        r.disable("a")
        assert r.is_enabled("a") is False

    def test_is_enabled_unknown_returns_false(self):
        r = AnalysisRegistry()
        assert r.is_enabled("unknown") is False


# ---------------------------------------------------------------------------
# Resolve
# ---------------------------------------------------------------------------

class TestResolve:
    def test_resolve_no_filters_returns_enabled(self):
        r = _reg("a", "b", "c")
        r.disable("c")
        resolved = {m.name for m in r.resolve()}
        assert "c" not in resolved
        assert {"a", "b"}.issubset(resolved)

    def test_resolve_by_analysis_type(self):
        r = _reg("technical", "quant", "macro")
        r.disable("macro")
        resolved = {m.name for m in r.resolve(analysis_type="technical")}
        assert "technical" in resolved
        # disabled module must be absent
        assert "macro" not in resolved

    def test_resolve_returns_list(self):
        r = _reg("x")
        assert isinstance(r.resolve(), list)

    def test_resolve_empty_registry_returns_empty(self):
        r = AnalysisRegistry()
        assert r.resolve() == []


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_health_check_returns_dict(self):
        r = _reg("a", "b")
        result = r.health_check()
        assert isinstance(result, dict)

    def test_health_check_has_registry_status(self):
        r = _reg("a")
        result = r.health_check()
        assert "status" in result

    def test_health_check_contains_module_count(self):
        r = _reg("a", "b", "c")
        result = r.health_check()
        # At minimum the total count should be accessible
        assert "total_modules" in result or "modules" in result or "registered" in result

    def test_health_check_empty_registry(self):
        r = AnalysisRegistry()
        result = r.health_check()
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# create_default()
# ---------------------------------------------------------------------------

class TestCreateDefault:
    def test_create_default_returns_registry(self):
        r = AnalysisRegistry.create_default()
        assert isinstance(r, AnalysisRegistry)

    def test_create_default_has_technical_enabled(self):
        r = AnalysisRegistry.create_default()
        assert r.is_enabled("technical")

    def test_create_default_has_quant_enabled(self):
        r = AnalysisRegistry.create_default()
        assert r.is_enabled("quant")

    def test_create_default_stubs_disabled(self):
        r = AnalysisRegistry.create_default()
        stub_names = [
            "fundamental", "macro", "sentiment", "intermarket",
            "futures", "options", "commodities", "forex", "crypto",
        ]
        for name in stub_names:
            assert r.is_enabled(name) is False, f"Expected {name!r} to be disabled"

    def test_create_default_stubs_present_in_all_modules(self):
        r = AnalysisRegistry.create_default()
        all_names = {m.name for m in r.all_modules()}
        expected_stubs = {
            "fundamental", "macro", "sentiment", "intermarket",
            "futures", "options", "commodities", "forex", "crypto",
        }
        assert expected_stubs.issubset(all_names)

    def test_create_default_total_module_count(self):
        r = AnalysisRegistry.create_default()
        assert len(r.all_modules()) >= 11  # technical + quant + 9 stubs

    def test_create_default_enabled_modules_exactly_two(self):
        r = AnalysisRegistry.create_default()
        enabled_names = {m.name for m in r.enabled_modules()}
        assert enabled_names == {"technical", "quant"}

    def test_create_default_technical_builds_features(self):
        import pandas as pd
        import numpy as np

        r = AnalysisRegistry.create_default()
        tech = r.get("technical")
        assert tech is not None
        n = 60
        data = pd.DataFrame({
            "open": np.linspace(100, 110, n),
            "high": np.linspace(101, 111, n),
            "low": np.linspace(99, 109, n),
            "close": np.linspace(100, 110, n),
            "volume": np.ones(n) * 1_000_000,
        })
        features = tech.build_features(data, {})
        assert isinstance(features, dict)
        assert "rsi_14" in features

    def test_create_default_quant_builds_features(self):
        import pandas as pd
        import numpy as np

        r = AnalysisRegistry.create_default()
        quant = r.get("quant")
        assert quant is not None
        n = 65
        data = pd.DataFrame({
            "open": np.linspace(100, 110, n),
            "high": np.linspace(101, 111, n),
            "low": np.linspace(99, 109, n),
            "close": np.linspace(100, 110, n),
            "volume": np.ones(n) * 1_000_000,
        })
        features = quant.build_features(data, {})
        assert isinstance(features, dict)
        assert "volatility_20d" in features

    def test_create_default_stub_health_check_is_stub(self):
        r = AnalysisRegistry.create_default()
        stub = r.get("fundamental")
        assert stub is not None
        hc = stub.health_check()
        assert hc.get("status") == "stub"

    def test_create_default_stub_build_features_returns_empty(self):
        import pandas as pd
        r = AnalysisRegistry.create_default()
        stub = r.get("macro")
        assert stub is not None
        result = stub.build_features(pd.DataFrame(), {})
        assert result == {}
