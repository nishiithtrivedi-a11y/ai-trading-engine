"""
Targeted tests for E3: Instrument cache path and TTL externalized.

Verifies that:
- Default InstrumentCacheConfig uses an absolute path under the project root.
- CWD change does not affect the default path.
- Custom path/TTL via constructor override works.
- InstrumentCacheConfig.from_env() reads INSTRUMENT_CACHE_PATH and
  INSTRUMENT_CACHE_TTL_HOURS env vars.
- KiteInstrumentMapper respects cache_config and cache_path arguments.
- Backward-compat: the old DEFAULT_CACHE_PATH and CACHE_MAX_AGE_HOURS
  module-level names still exist.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.data.instrument_mapper import (
    CACHE_MAX_AGE_HOURS,
    DEFAULT_CACHE_PATH,
    InstrumentCacheConfig,
    KiteInstrumentMapper,
    _PROJECT_ROOT,
)


# ---------------------------------------------------------------------------
# InstrumentCacheConfig defaults
# ---------------------------------------------------------------------------

class TestInstrumentCacheConfigDefaults:
    def test_default_cache_path_is_absolute(self):
        cfg = InstrumentCacheConfig()
        assert cfg.cache_path.is_absolute(), (
            f"Default cache_path must be absolute, got: {cfg.cache_path}"
        )

    def test_default_cache_path_under_project_root(self):
        cfg = InstrumentCacheConfig()
        # Path must be under the project root
        assert str(cfg.cache_path).startswith(str(_PROJECT_ROOT)), (
            f"Expected path under {_PROJECT_ROOT}, got {cfg.cache_path}"
        )

    def test_default_max_age_hours(self):
        cfg = InstrumentCacheConfig()
        assert cfg.max_age_hours == 24

    def test_cwd_change_does_not_affect_default_path(self, tmp_path, monkeypatch):
        """Changing CWD must not change the resolved default cache path."""
        monkeypatch.chdir(tmp_path)
        cfg = InstrumentCacheConfig()
        assert cfg.cache_path.is_absolute()
        assert not str(cfg.cache_path).startswith(str(tmp_path))


# ---------------------------------------------------------------------------
# InstrumentCacheConfig custom values
# ---------------------------------------------------------------------------

class TestInstrumentCacheConfigCustom:
    def test_custom_path(self, tmp_path):
        custom = tmp_path / "my_cache.csv"
        cfg = InstrumentCacheConfig(cache_path=custom)
        assert cfg.cache_path == custom

    def test_custom_ttl(self):
        cfg = InstrumentCacheConfig(max_age_hours=48)
        assert cfg.max_age_hours == 48


# ---------------------------------------------------------------------------
# InstrumentCacheConfig.from_env()
# ---------------------------------------------------------------------------

class TestFromEnv:
    def test_no_env_vars_gives_defaults(self, monkeypatch):
        monkeypatch.delenv("INSTRUMENT_CACHE_PATH", raising=False)
        monkeypatch.delenv("INSTRUMENT_CACHE_TTL_HOURS", raising=False)
        cfg = InstrumentCacheConfig.from_env()
        assert cfg.cache_path.is_absolute()
        assert cfg.max_age_hours == 24

    def test_absolute_cache_path_from_env(self, tmp_path, monkeypatch):
        target = tmp_path / "instruments.csv"
        monkeypatch.setenv("INSTRUMENT_CACHE_PATH", str(target))
        monkeypatch.delenv("INSTRUMENT_CACHE_TTL_HOURS", raising=False)
        cfg = InstrumentCacheConfig.from_env()
        assert cfg.cache_path == target

    def test_relative_cache_path_resolved_against_project_root(self, monkeypatch):
        monkeypatch.setenv("INSTRUMENT_CACHE_PATH", "custom/cache.csv")
        monkeypatch.delenv("INSTRUMENT_CACHE_TTL_HOURS", raising=False)
        cfg = InstrumentCacheConfig.from_env()
        assert cfg.cache_path.is_absolute()
        assert cfg.cache_path == _PROJECT_ROOT / "custom" / "cache.csv"

    def test_ttl_from_env(self, monkeypatch):
        monkeypatch.delenv("INSTRUMENT_CACHE_PATH", raising=False)
        monkeypatch.setenv("INSTRUMENT_CACHE_TTL_HOURS", "12")
        cfg = InstrumentCacheConfig.from_env()
        assert cfg.max_age_hours == 12

    def test_invalid_ttl_falls_back_to_24(self, monkeypatch):
        monkeypatch.delenv("INSTRUMENT_CACHE_PATH", raising=False)
        monkeypatch.setenv("INSTRUMENT_CACHE_TTL_HOURS", "not_a_number")
        cfg = InstrumentCacheConfig.from_env()
        assert cfg.max_age_hours == 24


# ---------------------------------------------------------------------------
# KiteInstrumentMapper respects cache_config / cache_path
# ---------------------------------------------------------------------------

class TestKiteInstrumentMapperConfig:
    def _mock_kite(self):
        return MagicMock()

    def test_default_cache_path_is_absolute(self):
        mapper = KiteInstrumentMapper(kite=self._mock_kite())
        assert mapper._cache_path.is_absolute()

    def test_cache_config_sets_path(self, tmp_path):
        p = tmp_path / "custom.csv"
        cfg = InstrumentCacheConfig(cache_path=p, max_age_hours=6)
        mapper = KiteInstrumentMapper(kite=self._mock_kite(), cache_config=cfg)
        assert mapper._cache_path == p
        assert mapper._max_age_hours == 6

    def test_explicit_cache_path_string_resolved(self, tmp_path):
        p = tmp_path / "another.csv"
        mapper = KiteInstrumentMapper(kite=self._mock_kite(), cache_path=str(p))
        assert mapper._cache_path == p
        assert mapper._cache_path.is_absolute()

    def test_legacy_relative_path_still_resolves(self, tmp_path, monkeypatch):
        """Old callers passing a relative string still get an absolute path."""
        monkeypatch.chdir(tmp_path)
        mapper = KiteInstrumentMapper(
            kite=self._mock_kite(),
            cache_path="data/cache/kite_instruments.csv",
        )
        assert mapper._cache_path.is_absolute()

    def test_cache_path_precedence_over_cache_config(self, tmp_path):
        """Explicit cache_path wins over cache_config.cache_path."""
        cfg = InstrumentCacheConfig(cache_path=tmp_path / "config_path.csv")
        explicit = tmp_path / "explicit.csv"
        mapper = KiteInstrumentMapper(
            kite=self._mock_kite(),
            cache_path=str(explicit),
            cache_config=cfg,
        )
        assert mapper._cache_path == explicit


# ---------------------------------------------------------------------------
# Backward-compat module-level names
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    def test_default_cache_path_still_exported(self):
        """DEFAULT_CACHE_PATH must still exist for existing callers."""
        assert DEFAULT_CACHE_PATH is not None
        assert isinstance(DEFAULT_CACHE_PATH, Path)

    def test_cache_max_age_hours_still_exported(self):
        assert CACHE_MAX_AGE_HOURS == 24
