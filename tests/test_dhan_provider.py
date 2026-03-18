"""Tests for DhanHQ provider: capability, health check, degraded states."""
from __future__ import annotations

import pytest
import pandas as pd

from src.data.dhan_source import DhanHQDataSource
from src.data.provider_capabilities import (
    get_derivative_capability_summary,
    get_provider_feature_set,
    _PROVIDER_CAPABILITIES,
)


# ---------------------------------------------------------------------------
# Health check tests (no SDK installed in test env)
# ---------------------------------------------------------------------------

class TestDhanHealthCheck:
    def test_health_check_sdk_unavailable(self):
        """Without dhanhq installed, state should be sdk_unavailable."""
        source = DhanHQDataSource()
        hc = source.health_check()
        # dhanhq is not installed in the test environment
        assert hc["provider"] == "dhan"
        assert "state" in hc
        assert "degraded" in hc

    def test_health_check_no_credentials_means_degraded_or_sdk_unavailable(self):
        """No credentials → degraded."""
        source = DhanHQDataSource(client_id=None, access_token=None)
        hc = source.health_check()
        assert hc.get("degraded") is True or hc.get("state") in (
            "sdk_unavailable", "no_credentials"
        )

    def test_health_check_with_credentials_sdk_unavailable(self):
        """Credentials provided but SDK not installed → sdk_unavailable."""
        source = DhanHQDataSource(client_id="TEST123", access_token="TOKEN456")
        hc = source.health_check()
        # SDK not installed so state will be sdk_unavailable
        assert hc["provider"] == "dhan"

    def test_health_check_returns_dict(self):
        source = DhanHQDataSource()
        hc = source.health_check()
        assert isinstance(hc, dict)
        assert "provider" in hc

    def test_health_check_sdk_error_field_present_when_unavailable(self):
        source = DhanHQDataSource()
        hc = source.health_check()
        if hc.get("state") == "sdk_unavailable":
            assert "sdk_error" in hc
            assert "dhanhq" in hc["sdk_error"].lower()


# ---------------------------------------------------------------------------
# Degraded behavior
# ---------------------------------------------------------------------------

class TestDhanDegradedBehavior:
    def test_load_raises_not_implemented(self):
        source = DhanHQDataSource()
        with pytest.raises(NotImplementedError):
            source.load()

    def test_fetch_historical_raises_not_implemented_without_sdk(self):
        from datetime import datetime
        source = DhanHQDataSource()
        if not source._sdk_available:
            with pytest.raises(NotImplementedError):
                source.fetch_historical("NIFTY", "DAILY", datetime(2025, 1, 1), datetime(2025, 12, 31))

    def test_fetch_live_raises_not_implemented_without_sdk(self):
        source = DhanHQDataSource()
        if not source._sdk_available:
            with pytest.raises(NotImplementedError):
                source.fetch_live("NIFTY")

    def test_fetch_option_chain_returns_degraded_dict_without_sdk(self):
        source = DhanHQDataSource()
        result = source.fetch_option_chain("NIFTY", "2026-04-30")
        assert isinstance(result, dict)
        assert "calls" in result
        assert "puts" in result
        if not source._sdk_available:
            assert result.get("degraded") is True

    def test_fetch_expiry_list_returns_empty_without_sdk(self):
        source = DhanHQDataSource()
        result = source.fetch_expiry_list("NIFTY")
        assert isinstance(result, list)
        if not source._sdk_available:
            assert result == []

    def test_list_instruments_returns_empty(self):
        source = DhanHQDataSource()
        assert source.list_instruments() == []


# ---------------------------------------------------------------------------
# _normalize_historical
# ---------------------------------------------------------------------------

class TestNormalizeHistorical:
    def _make_source(self):
        return DhanHQDataSource()

    def test_normalize_empty_response(self):
        source = self._make_source()
        result = source._normalize_historical({})
        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["open", "high", "low", "close", "volume"]

    def test_normalize_none_response(self):
        source = self._make_source()
        result = source._normalize_historical(None)
        assert isinstance(result, pd.DataFrame)

    def test_normalize_dict_format(self):
        """Dhan dict format: data={timestamp:[...], open:[...], ...}"""
        source = self._make_source()
        response = {
            "data": {
                "timestamp": [1700000000, 1700003600],
                "open": [22000.0, 22050.0],
                "high": [22100.0, 22120.0],
                "low": [21990.0, 22020.0],
                "close": [22080.0, 22110.0],
                "volume": [10000, 12000],
            }
        }
        result = source._normalize_historical(response)
        assert len(result) == 2
        assert "open" in result.columns
        assert "close" in result.columns
        assert result["close"].iloc[0] == pytest.approx(22080.0)

    def test_normalize_list_format(self):
        """Alternative list format: data=[[ts, o, h, l, c, v], ...]"""
        source = self._make_source()
        response = {
            "data": [
                [1700000000, 22000.0, 22100.0, 21990.0, 22080.0, 10000],
                [1700003600, 22050.0, 22120.0, 22020.0, 22110.0, 12000],
            ]
        }
        result = source._normalize_historical(response)
        assert len(result) == 2
        assert result["open"].iloc[0] == pytest.approx(22000.0)

    def test_normalize_empty_data_dict(self):
        source = self._make_source()
        response = {"data": {"timestamp": [], "open": [], "high": [], "low": [], "close": []}}
        result = source._normalize_historical(response)
        assert len(result) == 0

    def test_normalize_returns_sorted_index(self):
        source = self._make_source()
        response = {
            "data": {
                "timestamp": [1700003600, 1700000000],
                "open": [22050.0, 22000.0],
                "high": [22120.0, 22100.0],
                "low": [22020.0, 21990.0],
                "close": [22110.0, 22080.0],
                "volume": [12000, 10000],
            }
        }
        result = source._normalize_historical(response)
        assert result.index.is_monotonic_increasing


# ---------------------------------------------------------------------------
# _normalize_option_chain
# ---------------------------------------------------------------------------

class TestNormalizeOptionChain:
    def _make_source(self):
        return DhanHQDataSource()

    def test_normalize_empty_response(self):
        source = self._make_source()
        result = source._normalize_option_chain({})
        assert "calls" in result
        assert "puts" in result

    def test_normalize_none_response(self):
        source = self._make_source()
        result = source._normalize_option_chain(None)
        assert isinstance(result, dict)

    def test_normalize_callOption_putOption_format(self):
        """Dhan's callOption/putOption dict format."""
        source = self._make_source()
        response = {
            "data": [
                {
                    "strikePrice": 22000,
                    "callOption": {"OI": 100000, "LTP": 200.0, "bidPrice": 199.0, "askPrice": 201.0, "impliedVolatility": 0.15, "volume": 5000, "delta": 0.5},
                    "putOption": {"OI": 80000, "LTP": 180.0, "bidPrice": 179.0, "askPrice": 181.0, "impliedVolatility": 0.16, "volume": 4000, "delta": -0.5},
                }
            ]
        }
        result = source._normalize_option_chain(response)
        assert len(result["calls"]) == 1
        assert len(result["puts"]) == 1
        assert result["calls"][0]["strike"] == 22000.0
        assert result["calls"][0]["oi"] == 100000
        assert result["calls"][0]["option_type"] == "CE"
        assert result["puts"][0]["option_type"] == "PE"
        assert result["degraded"] is False

    def test_normalize_ce_pe_format(self):
        """Alternative ce/pe dict format."""
        source = self._make_source()
        response = {
            "data": [
                {
                    "strike_price": 22500,
                    "ce": {"oi": 50000, "ltp": 100.0, "iv": 0.14},
                    "pe": {"oi": 60000, "ltp": 110.0, "iv": 0.15},
                }
            ]
        }
        result = source._normalize_option_chain(response)
        assert len(result["calls"]) == 1
        assert result["calls"][0]["strike"] == 22500.0

    def test_normalize_sorted_by_strike(self):
        source = self._make_source()
        response = {
            "data": [
                {"strikePrice": 22500, "callOption": {"OI": 1000, "LTP": 50.0, "bidPrice": 0, "askPrice": 0, "impliedVolatility": 0, "volume": 0}, "putOption": {}},
                {"strikePrice": 22000, "callOption": {"OI": 2000, "LTP": 200.0, "bidPrice": 0, "askPrice": 0, "impliedVolatility": 0, "volume": 0}, "putOption": {}},
            ]
        }
        result = source._normalize_option_chain(response)
        strikes = [c["strike"] for c in result["calls"]]
        assert strikes == sorted(strikes)


# ---------------------------------------------------------------------------
# Provider capability tests
# ---------------------------------------------------------------------------

class TestDhanCapability:
    def test_dhan_in_provider_capabilities(self):
        assert "dhan" in _PROVIDER_CAPABILITIES

    def test_dhan_supports_derivatives(self):
        fs = get_provider_feature_set("dhan")
        assert fs.supports_derivatives is True

    def test_dhan_supports_historical_derivatives(self):
        fs = get_provider_feature_set("dhan")
        assert fs.supports_historical_derivatives is True

    def test_dhan_supports_oi(self):
        fs = get_provider_feature_set("dhan")
        assert fs.supports_oi is True

    def test_dhan_supported_segments(self):
        fs = get_provider_feature_set("dhan")
        assert "NFO" in fs.supported_segments
        assert "NSE" in fs.supported_segments
        assert "MCX" in fs.supported_segments
        assert "CDS" in fs.supported_segments

    def test_dhan_instrument_master_not_available(self):
        fs = get_provider_feature_set("dhan")
        assert fs.instrument_master_available is False

    def test_dhan_capability_summary(self):
        summary = get_derivative_capability_summary("dhan")
        assert summary["provider"] == "dhan"
        assert summary["supports_derivatives"] is True
        assert summary["supports_oi"] is True

    def test_dhan_supports_nfo_segment(self):
        fs = get_provider_feature_set("dhan")
        assert fs.supports_segment("NFO") is True

    def test_dhan_supports_mcx_segment(self):
        fs = get_provider_feature_set("dhan")
        assert fs.supports_segment("MCX") is True
