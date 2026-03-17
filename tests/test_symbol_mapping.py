"""Tests for NSE symbol normalization and mapping."""

import pytest

from src.data.symbol_mapping import SymbolMapper


class TestSymbolMapper:

    def setup_method(self):
        self.mapper = SymbolMapper()

    # --- normalize ---

    def test_normalize_bare(self):
        assert self.mapper.normalize("RELIANCE") == "RELIANCE"

    def test_normalize_lowercase(self):
        assert self.mapper.normalize("reliance") == "RELIANCE"

    def test_normalize_yahoo_ns(self):
        assert self.mapper.normalize("RELIANCE.NS") == "RELIANCE"

    def test_normalize_yahoo_bo(self):
        assert self.mapper.normalize("RELIANCE.BO") == "RELIANCE"

    def test_normalize_upstox_format(self):
        assert self.mapper.normalize("NSE_EQ|RELIANCE") == "RELIANCE"

    def test_normalize_upstox_fo(self):
        assert self.mapper.normalize("NSE_FO|NIFTY") == "NIFTY"

    def test_normalize_exchange_prefixed_symbol(self):
        assert self.mapper.normalize("NSE:RELIANCE") == "RELIANCE"

    def test_normalize_whitespace(self):
        assert self.mapper.normalize("  INFY  ") == "INFY"

    # --- to_yahoo ---

    def test_to_yahoo_bare(self):
        assert self.mapper.to_yahoo("RELIANCE") == "RELIANCE.NS"

    def test_to_yahoo_already_suffixed(self):
        assert self.mapper.to_yahoo("RELIANCE.NS") == "RELIANCE.NS"

    def test_to_yahoo_custom_exchange(self):
        assert self.mapper.to_yahoo("RELIANCE", exchange=".BO") == "RELIANCE.BO"

    # --- to_zerodha ---

    def test_to_zerodha_strips_suffix(self):
        assert self.mapper.to_zerodha("RELIANCE.NS") == "RELIANCE"

    def test_to_zerodha_bare(self):
        assert self.mapper.to_zerodha("RELIANCE") == "RELIANCE"

    # --- to_upstox ---

    def test_to_upstox_default_segment(self):
        assert self.mapper.to_upstox("RELIANCE") == "NSE_EQ|RELIANCE"

    def test_to_upstox_custom_segment(self):
        assert self.mapper.to_upstox("NIFTY", segment="NSE_INDEX") == "NSE_INDEX|NIFTY"

    def test_to_upstox_from_yahoo(self):
        assert self.mapper.to_upstox("TCS.NS") == "NSE_EQ|TCS"

    # --- canonical / provider mapping ---

    def test_to_canonical_from_bare(self):
        assert self.mapper.to_canonical("RELIANCE") == "RELIANCE.NS"

    def test_to_canonical_from_exchange_prefixed(self):
        assert self.mapper.to_canonical("NSE:RELIANCE") == "RELIANCE.NS"

    def test_to_provider_symbol_zerodha(self):
        assert self.mapper.to_provider_symbol("zerodha", "RELIANCE.NS") == "RELIANCE"

    def test_to_provider_symbol_upstox(self):
        assert self.mapper.to_provider_symbol("upstox", "RELIANCE.NS") == "NSE_EQ|RELIANCE"

    def test_from_provider_symbol_returns_canonical(self):
        assert self.mapper.from_provider_symbol("upstox", "NSE_EQ|TCS") == "TCS.NS"

    # --- from_filename ---

    def test_from_filename_daily(self):
        assert self.mapper.from_filename("RELIANCE_1D.csv") == "RELIANCE"

    def test_from_filename_5m(self):
        assert self.mapper.from_filename("TCS_5m.csv") == "TCS"

    def test_from_filename_15m(self):
        assert self.mapper.from_filename("INFY_15m.csv") == "INFY"

    def test_from_filename_1h(self):
        assert self.mapper.from_filename("HDFCBANK_1h.csv") == "HDFCBANK"

    def test_from_filename_with_path(self):
        assert self.mapper.from_filename("data/RELIANCE_1D.csv") == "RELIANCE"

    def test_from_filename_no_timeframe(self):
        assert self.mapper.from_filename("RELIANCE.csv") == "RELIANCE"

    # --- aliases ---

    def test_alias(self):
        self.mapper.add_alias("NIFTY 50", "NIFTY50")
        assert self.mapper.normalize("NIFTY 50") == "NIFTY50"

    # --- batch operations ---

    def test_batch_normalize_deduplicates(self):
        result = self.mapper.batch_normalize(
            ["RELIANCE.NS", "RELIANCE", "NSE_EQ|RELIANCE", "TCS.NS"]
        )
        assert result == ["RELIANCE", "TCS"]

    def test_batch_to_yahoo(self):
        result = self.mapper.batch_to_yahoo(["RELIANCE", "TCS", "INFY"])
        assert result == ["RELIANCE.NS", "TCS.NS", "INFY.NS"]
