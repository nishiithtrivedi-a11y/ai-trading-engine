"""
Targeted tests for E2: Kite API historical range limits externalized to YAML.

Verifies that:
- Each interval maps to the correct max_days via _get_max_days_for_interval().
- ZerodhaDataSource._max_days_per_request() returns correct values per Timeframe.
- Missing config key falls back to hardcoded _KITE_RANGE_DEFAULTS.
- Config overrides work when the YAML is loaded.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from src.data.base import Timeframe
from src.data.sources import (
    _KITE_RANGE_DEFAULTS,
    _get_max_days_for_interval,
    ZerodhaDataSource,
)


# ---------------------------------------------------------------------------
# _get_max_days_for_interval — unit tests
# ---------------------------------------------------------------------------

class TestGetMaxDaysForInterval:
    def test_minute_default(self):
        assert _get_max_days_for_interval("minute") == 60

    def test_5minute_default(self):
        assert _get_max_days_for_interval("5minute") == 100

    def test_15minute_default(self):
        assert _get_max_days_for_interval("15minute") == 100

    def test_60minute_default(self):
        assert _get_max_days_for_interval("60minute") == 400

    def test_day_default(self):
        assert _get_max_days_for_interval("day") == 2000

    def test_unknown_interval_returns_conservative(self):
        # Should fall back to 60 (most conservative) for unknown intervals
        result = _get_max_days_for_interval("999minute")
        assert result == 60

    def test_all_defaults_covered(self):
        for interval, expected in _KITE_RANGE_DEFAULTS.items():
            assert _get_max_days_for_interval(interval) == expected


# ---------------------------------------------------------------------------
# ZerodhaDataSource._max_days_per_request — Timeframe mapping
# ---------------------------------------------------------------------------

class TestMaxDaysPerRequest:
    def test_minute1(self):
        assert ZerodhaDataSource._max_days_per_request(Timeframe.MINUTE_1) == 60

    def test_minute5(self):
        assert ZerodhaDataSource._max_days_per_request(Timeframe.MINUTE_5) == 100

    def test_minute15(self):
        assert ZerodhaDataSource._max_days_per_request(Timeframe.MINUTE_15) == 100

    def test_hourly(self):
        assert ZerodhaDataSource._max_days_per_request(Timeframe.HOURLY) == 400

    def test_daily(self):
        assert ZerodhaDataSource._max_days_per_request(Timeframe.DAILY) == 2000


# ---------------------------------------------------------------------------
# Fallback behavior when config is absent / malformed
# ---------------------------------------------------------------------------

class TestConfigFallback:
    def test_missing_file_falls_back_to_defaults(self, tmp_path, monkeypatch):
        """When data_providers.yaml is absent, _load_kite_range_config() uses defaults."""
        import src.data.sources as sources_mod
        monkeypatch.setattr(sources_mod, "_DATA_PROVIDERS_YAML", tmp_path / "missing.yaml")
        from src.data.sources import _load_kite_range_config
        result = _load_kite_range_config()
        assert result["minute"] == 60
        assert result["day"] == 2000

    def test_missing_kite_key_falls_back(self, tmp_path, monkeypatch):
        """YAML with no 'kite' section still uses defaults."""
        cfg = tmp_path / "data_providers.yaml"
        cfg.write_text("default_provider: zerodha\n", encoding="utf-8")
        import src.data.sources as sources_mod
        monkeypatch.setattr(sources_mod, "_DATA_PROVIDERS_YAML", cfg)
        from src.data.sources import _load_kite_range_config
        result = _load_kite_range_config()
        assert result["minute"] == 60
        assert result["60minute"] == 400

    def test_config_override_applies(self, tmp_path, monkeypatch):
        """Override in YAML is respected over the hardcoded default."""
        cfg_data = {
            "kite": {
                "historical_range_days": {
                    "minute": 90,
                    "day": 3000,
                }
            }
        }
        cfg = tmp_path / "data_providers.yaml"
        cfg.write_text(yaml.dump(cfg_data), encoding="utf-8")

        import src.data.sources as sources_mod
        monkeypatch.setattr(sources_mod, "_DATA_PROVIDERS_YAML", cfg)
        from src.data.sources import _load_kite_range_config
        result = _load_kite_range_config()
        assert result["minute"] == 90
        assert result["day"] == 3000
        # Non-overridden key stays at default
        assert result["5minute"] == 100

    def test_invalid_value_in_config_skipped(self, tmp_path, monkeypatch):
        """Non-integer value in YAML is skipped gracefully."""
        cfg_data = {
            "kite": {
                "historical_range_days": {
                    "minute": "not_an_int",
                    "day": 2000,
                }
            }
        }
        cfg = tmp_path / "data_providers.yaml"
        cfg.write_text(yaml.dump(cfg_data), encoding="utf-8")

        import src.data.sources as sources_mod
        monkeypatch.setattr(sources_mod, "_DATA_PROVIDERS_YAML", cfg)
        from src.data.sources import _load_kite_range_config
        result = _load_kite_range_config()
        # 'minute' was skipped — falls back to default
        assert result["minute"] == 60
        # 'day' was valid
        assert result["day"] == 2000
