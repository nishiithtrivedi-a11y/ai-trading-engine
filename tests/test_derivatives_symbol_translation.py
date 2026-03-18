"""
Tests for to_provider_symbol with Phase 2 derivative implementations.

These tests verify the full translation pipeline:
canonical string -> provider-native symbol string.
"""
from __future__ import annotations

import pytest

from src.instruments.normalization import to_provider_symbol


class TestToProviderSymbolDerivatives:
    # ------------------------------------------------------------------
    # Equity translations
    # ------------------------------------------------------------------

    def test_equity_to_zerodha_bare_symbol(self):
        assert to_provider_symbol("NSE:RELIANCE-EQ", "zerodha") == "RELIANCE"

    def test_equity_to_kite_alias(self):
        assert to_provider_symbol("NSE:RELIANCE-EQ", "kite") == "RELIANCE"

    def test_bse_equity_to_zerodha(self):
        assert to_provider_symbol("BSE:TCS-EQ", "zerodha") == "TCS"

    def test_equity_to_upstox_nse(self):
        assert to_provider_symbol("NSE:RELIANCE-EQ", "upstox") == "NSE_EQ|RELIANCE"

    def test_equity_to_upstox_bse(self):
        assert to_provider_symbol("BSE:TCS-EQ", "upstox") == "BSE_EQ|TCS"

    def test_equity_to_csv(self):
        assert to_provider_symbol("NSE:RELIANCE-EQ", "csv") == "RELIANCE"

    def test_equity_to_indian_csv(self):
        assert to_provider_symbol("NSE:INFY-EQ", "indian_csv") == "INFY"

    # ------------------------------------------------------------------
    # Future translations
    # ------------------------------------------------------------------

    def test_nfo_future_to_zerodha(self):
        result = to_provider_symbol("NFO:NIFTY-2026-04-30-FUT", "zerodha")
        assert result == "NIFTY26APRFUT"

    def test_nfo_future_to_upstox(self):
        result = to_provider_symbol("NFO:NIFTY-2026-04-30-FUT", "upstox")
        assert result == "NSE_FO|NIFTY26APRFUT"

    def test_mcx_future_to_zerodha(self):
        result = to_provider_symbol("MCX:GOLD-2026-04-30-FUT", "zerodha")
        assert result == "GOLD26APRFUT"

    def test_mcx_future_to_upstox(self):
        result = to_provider_symbol("MCX:GOLD-2026-04-30-FUT", "upstox")
        assert result == "MCX_FO|GOLD26APRFUT"

    def test_cds_future_to_zerodha(self):
        result = to_provider_symbol("CDS:USDINR-2026-04-30-FUT", "zerodha")
        assert result == "USDINR26APRFUT"

    def test_cds_future_to_upstox(self):
        result = to_provider_symbol("CDS:USDINR-2026-04-30-FUT", "upstox")
        assert result == "CDS_FO|USDINR26APRFUT"

    def test_banknifty_future_to_zerodha(self):
        result = to_provider_symbol("NFO:BANKNIFTY-2026-03-26-FUT", "zerodha")
        assert result == "BANKNIFTY26MARFUT"

    def test_future_to_csv_returns_bare_symbol(self):
        result = to_provider_symbol("NFO:NIFTY-2026-04-30-FUT", "csv")
        assert result == "NIFTY"

    # ------------------------------------------------------------------
    # Option translations
    # ------------------------------------------------------------------

    def test_call_option_to_zerodha(self):
        result = to_provider_symbol("NFO:NIFTY-2026-04-30-24500-CE", "zerodha")
        assert result == "NIFTY26APR24500CE"

    def test_put_option_to_zerodha(self):
        result = to_provider_symbol("NFO:NIFTY-2026-04-30-24500-PE", "zerodha")
        assert result == "NIFTY26APR24500PE"

    def test_call_option_to_upstox(self):
        result = to_provider_symbol("NFO:NIFTY-2026-04-30-24500-CE", "upstox")
        assert result == "NSE_FO|NIFTY26APR24500CE"

    def test_put_option_ends_pe(self):
        result = to_provider_symbol("NFO:BANKNIFTY-2026-04-30-48000-PE", "zerodha")
        assert result.endswith("PE")
        assert "BANKNIFTY" in result

    def test_option_to_csv_returns_bare_symbol(self):
        result = to_provider_symbol("NFO:NIFTY-2026-04-30-24500-CE", "csv")
        assert result == "NIFTY"

    # ------------------------------------------------------------------
    # Unknown provider
    # ------------------------------------------------------------------

    def test_unknown_provider_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            to_provider_symbol("NSE:RELIANCE-EQ", "unknown_xyz")

    def test_angel_provider_raises_not_implemented(self):
        with pytest.raises(NotImplementedError, match="angel"):
            to_provider_symbol("NSE:INFY-EQ", "angel")

    def test_fyers_provider_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            to_provider_symbol("NSE:RELIANCE-EQ", "fyers")

    # ------------------------------------------------------------------
    # Case insensitive provider
    # ------------------------------------------------------------------

    def test_zerodha_case_insensitive(self):
        result = to_provider_symbol("NSE:RELIANCE-EQ", "Zerodha")
        assert result == "RELIANCE"

    def test_upstox_case_insensitive(self):
        result = to_provider_symbol("NSE:RELIANCE-EQ", "UPSTOX")
        assert result == "NSE_EQ|RELIANCE"

    def test_csv_case_insensitive(self):
        result = to_provider_symbol("NSE:RELIANCE-EQ", "CSV")
        assert result == "RELIANCE"
