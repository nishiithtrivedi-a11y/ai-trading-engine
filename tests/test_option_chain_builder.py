"""Tests for OptionChainBuilder, OptionChain, OptionStrike."""
from __future__ import annotations

import pytest
from datetime import date, datetime

from src.analysis.derivatives.options.chain import (
    OptionChain,
    OptionChainBuilder,
    OptionStrike,
)


class TestOptionStrike:
    def test_total_oi_both_sides(self):
        s = OptionStrike(strike=22000.0, ce_oi=100000, pe_oi=80000)
        assert s.total_oi == 180000

    def test_total_oi_one_side_none(self):
        s = OptionStrike(strike=22000.0, ce_oi=100000, pe_oi=None)
        assert s.total_oi == 100000

    def test_total_oi_both_none(self):
        s = OptionStrike(strike=22000.0)
        assert s.total_oi == 0

    def test_pcr_valid(self):
        s = OptionStrike(strike=22000.0, ce_oi=100000, pe_oi=80000)
        assert s.pcr == pytest.approx(0.8)

    def test_pcr_ce_oi_zero_returns_none(self):
        s = OptionStrike(strike=22000.0, ce_oi=0, pe_oi=50000)
        assert s.pcr is None

    def test_pcr_ce_oi_none_returns_none(self):
        s = OptionStrike(strike=22000.0, ce_oi=None, pe_oi=50000)
        assert s.pcr is None


class TestOptionChain:
    def _make_chain(self, spot=22000.0) -> OptionChain:
        strikes = [
            OptionStrike(strike=21500.0, ce_oi=50000, pe_oi=200000),
            OptionStrike(strike=21750.0, ce_oi=80000, pe_oi=150000),
            OptionStrike(strike=22000.0, ce_oi=120000, pe_oi=120000, ce_ltp=200.0, pe_ltp=180.0),
            OptionStrike(strike=22250.0, ce_oi=150000, pe_oi=80000, ce_ltp=100.0, pe_ltp=280.0),
            OptionStrike(strike=22500.0, ce_oi=200000, pe_oi=50000),
        ]
        return OptionChain(
            underlying="NIFTY",
            expiry=date(2026, 4, 30),
            spot_price=spot,
            strikes=strikes,
        )

    def test_call_oi_total(self):
        chain = self._make_chain()
        assert chain.call_oi_total == 50000 + 80000 + 120000 + 150000 + 200000

    def test_put_oi_total(self):
        chain = self._make_chain()
        assert chain.put_oi_total == 200000 + 150000 + 120000 + 80000 + 50000

    def test_chain_pcr(self):
        chain = self._make_chain()
        expected = chain.put_oi_total / chain.call_oi_total
        assert chain.chain_pcr == pytest.approx(expected)

    def test_chain_pcr_no_call_oi_returns_none(self):
        chain = OptionChain(underlying="X", expiry=date(2026, 4, 30))
        assert chain.chain_pcr is None

    def test_get_atm_strike_nearest_to_spot(self):
        chain = self._make_chain(spot=22000.0)
        assert chain.get_atm_strike() == 22000.0

    def test_get_atm_strike_between_strikes(self):
        chain = self._make_chain(spot=22100.0)
        # 22000 is 100 away, 22250 is 150 away → ATM = 22000
        assert chain.get_atm_strike() == 22000.0

    def test_get_atm_strike_no_spot_returns_none(self):
        chain = OptionChain(underlying="X", expiry=date(2026, 4, 30))
        chain.strikes = [OptionStrike(strike=22000.0)]
        assert chain.get_atm_strike() is None

    def test_get_atm_strike_no_strikes_returns_none(self):
        chain = OptionChain(underlying="X", expiry=date(2026, 4, 30), spot_price=22000)
        assert chain.get_atm_strike() is None

    def test_sorted_strikes_is_ordered(self):
        chain = self._make_chain()
        sorted_s = chain.sorted_strikes
        for i in range(len(sorted_s) - 1):
            assert sorted_s[i].strike <= sorted_s[i + 1].strike

    def test_get_strikes_around_atm(self):
        chain = self._make_chain(spot=22000.0)
        around = chain.get_strikes_around_atm(n=1)
        # ATM=22000, n=1 → should include 21750, 22000, 22250
        strikes_in = [s.strike for s in around]
        assert 22000.0 in strikes_in

    def test_to_dict_has_required_keys(self):
        chain = self._make_chain()
        d = chain.to_dict()
        assert "underlying" in d
        assert "expiry" in d
        assert "chain_pcr" in d
        assert "call_oi_total" in d
        assert "put_oi_total" in d
        assert "strike_count" in d
        assert d["strike_count"] == 5


class TestOptionChainBuilder:
    def _builder(self) -> OptionChainBuilder:
        return OptionChainBuilder()

    def test_from_dhan_response_basic(self):
        dhan_chain = {
            "calls": [
                {"strike": 22000.0, "oi": 100000, "ltp": 200.0, "bid": 199.0, "ask": 201.0, "iv": 0.15, "volume": 5000, "delta": 0.5, "theta": -1.0, "gamma": 0.001, "vega": 10.0, "option_type": "CE", "source": "dhan"},
                {"strike": 22500.0, "oi": 150000, "ltp": 50.0, "bid": 49.0, "ask": 51.0, "iv": 0.18, "volume": 3000, "delta": 0.2, "theta": -0.5, "gamma": 0.0005, "vega": 5.0, "option_type": "CE", "source": "dhan"},
            ],
            "puts": [
                {"strike": 22000.0, "oi": 80000, "ltp": 180.0, "bid": 179.0, "ask": 181.0, "iv": 0.16, "volume": 4000, "delta": -0.5, "theta": -1.0, "gamma": 0.001, "vega": 10.0, "option_type": "PE", "source": "dhan"},
            ],
            "degraded": False,
        }
        builder = self._builder()
        chain = builder.from_dhan_response("NIFTY", date(2026, 4, 30), dhan_chain)

        assert chain.underlying == "NIFTY"
        assert chain.provider == "dhan"
        assert chain.degraded is False
        assert len(chain.strikes) == 2  # 22000 and 22500

        # Strike 22000 should have both CE and PE
        s22000 = next(s for s in chain.strikes if s.strike == 22000.0)
        assert s22000.ce_oi == 100000
        assert s22000.pe_oi == 80000
        assert s22000.ce_source == "dhan"
        assert s22000.pe_source == "dhan"

    def test_from_dhan_response_empty(self):
        builder = self._builder()
        chain = builder.from_dhan_response("NIFTY", date(2026, 4, 30), {})
        assert len(chain.strikes) == 0

    def test_from_dhan_response_degraded(self):
        builder = self._builder()
        chain = builder.from_dhan_response("NIFTY", date(2026, 4, 30), {"degraded": True, "calls": [], "puts": []})
        assert chain.degraded is True

    def test_from_normalized_dict_list_ce_pe(self):
        rows = [
            {"strike": 22000, "option_type": "CE", "ltp": 200.0, "oi": 100000},
            {"strike": 22000, "option_type": "PE", "ltp": 180.0, "oi": 80000},
            {"strike": 22500, "option_type": "CE", "ltp": 50.0, "oi": 150000},
        ]
        builder = self._builder()
        chain = builder.from_normalized_dict_list("NIFTY", date(2026, 4, 30), rows)

        assert chain.underlying == "NIFTY"
        assert len(chain.strikes) == 2
        s22000 = next(s for s in chain.strikes if s.strike == 22000.0)
        assert s22000.ce_ltp == pytest.approx(200.0)
        assert s22000.pe_ltp == pytest.approx(180.0)

    def test_from_normalized_dict_list_call_put_strings(self):
        """Test that 'CALL' and 'PUT' are also recognized."""
        rows = [
            {"strike": 22000, "option_type": "CALL", "ltp": 200.0, "oi": 100000},
            {"strike": 22000, "option_type": "PUT", "ltp": 180.0, "oi": 80000},
        ]
        builder = self._builder()
        chain = builder.from_normalized_dict_list("NIFTY", date(2026, 4, 30), rows)
        s = chain.strikes[0]
        assert s.ce_ltp == pytest.approx(200.0)
        assert s.pe_ltp == pytest.approx(180.0)

    def test_from_normalized_dict_list_provider_name(self):
        rows = [{"strike": 22000, "option_type": "CE", "ltp": 200.0}]
        builder = self._builder()
        chain = builder.from_normalized_dict_list("NIFTY", date(2026, 4, 30), rows, provider="zerodha")
        assert chain.provider == "zerodha"
        s = chain.strikes[0]
        assert s.ce_source == "zerodha"

    def test_from_normalized_dict_list_empty_rows(self):
        builder = self._builder()
        chain = builder.from_normalized_dict_list("NIFTY", date(2026, 4, 30), [])
        assert len(chain.strikes) == 0

    def test_from_dhan_response_underlying_uppercased(self):
        builder = self._builder()
        chain = builder.from_dhan_response("nifty", date(2026, 4, 30), {})
        assert chain.underlying == "NIFTY"
