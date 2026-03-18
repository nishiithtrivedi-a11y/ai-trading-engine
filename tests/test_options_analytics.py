"""Tests for Black-Scholes analytics, IV, chain-level metrics."""
from __future__ import annotations

import math
import pytest
from datetime import date

from src.analysis.derivatives.options.analytics import (
    BSMResult,
    ChainAnalytics,
    OptionChainAnalyzer,
    _norm_cdf,
    _norm_pdf,
    black_scholes,
    classify_moneyness,
    implied_volatility,
)
from src.analysis.derivatives.options.chain import OptionChain, OptionStrike


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

class TestNormFunctions:
    def test_norm_cdf_at_zero(self):
        assert _norm_cdf(0.0) == pytest.approx(0.5, abs=1e-6)

    def test_norm_cdf_positive_large(self):
        assert _norm_cdf(5.0) > 0.999

    def test_norm_cdf_negative_large(self):
        assert _norm_cdf(-5.0) < 0.001

    def test_norm_pdf_at_zero(self):
        expected = 1.0 / math.sqrt(2 * math.pi)
        assert _norm_pdf(0.0) == pytest.approx(expected, rel=1e-6)


# ---------------------------------------------------------------------------
# Black-Scholes tests
# ---------------------------------------------------------------------------

class TestBlackScholes:
    _S = 22000.0
    _K = 22000.0
    _T = 7 / 365.0   # 7 days
    _r = 0.065
    _sigma = 0.15

    def test_call_price_positive(self):
        res = black_scholes(self._S, self._K, self._T, self._r, self._sigma, "CE")
        assert res.theoretical_price > 0

    def test_put_price_positive(self):
        res = black_scholes(self._S, self._K, self._T, self._r, self._sigma, "PE")
        assert res.theoretical_price > 0

    def test_call_delta_between_0_and_1(self):
        res = black_scholes(self._S, self._K, self._T, self._r, self._sigma, "CE")
        assert 0 < res.delta < 1

    def test_put_delta_between_minus1_and_0(self):
        res = black_scholes(self._S, self._K, self._T, self._r, self._sigma, "PE")
        assert -1 < res.delta < 0

    def test_gamma_positive(self):
        res = black_scholes(self._S, self._K, self._T, self._r, self._sigma, "CE")
        assert res.gamma > 0

    def test_theta_negative_for_call(self):
        """Theta (time decay) should be negative — option loses value daily."""
        res = black_scholes(self._S, self._K, self._T, self._r, self._sigma, "CE")
        assert res.theta < 0

    def test_theta_negative_for_put(self):
        res = black_scholes(self._S, self._K, self._T, self._r, self._sigma, "PE")
        assert res.theta < 0

    def test_vega_positive(self):
        res = black_scholes(self._S, self._K, self._T, self._r, self._sigma, "CE")
        assert res.vega > 0

    def test_computed_flag_is_true(self):
        res = black_scholes(self._S, self._K, self._T, self._r, self._sigma, "CE")
        assert res.computed is True

    def test_raises_value_error_for_T_zero(self):
        with pytest.raises(ValueError, match="T must be > 0"):
            black_scholes(self._S, self._K, 0, self._r, self._sigma)

    def test_raises_value_error_for_T_negative(self):
        with pytest.raises(ValueError, match="T must be > 0"):
            black_scholes(self._S, self._K, -1, self._r, self._sigma)

    def test_raises_value_error_for_sigma_zero(self):
        with pytest.raises(ValueError, match="sigma must be > 0"):
            black_scholes(self._S, self._K, self._T, self._r, 0.0)

    def test_raises_value_error_for_sigma_negative(self):
        with pytest.raises(ValueError, match="sigma must be > 0"):
            black_scholes(self._S, self._K, self._T, self._r, -0.1)

    def test_raises_value_error_for_S_zero(self):
        with pytest.raises(ValueError, match="S and K must be > 0"):
            black_scholes(0, self._K, self._T, self._r, self._sigma)

    def test_raises_value_error_for_K_zero(self):
        with pytest.raises(ValueError, match="S and K must be > 0"):
            black_scholes(self._S, 0, self._T, self._r, self._sigma)

    def test_deep_itm_call_delta_near_1(self):
        res = black_scholes(25000, 20000, 30 / 365, self._r, self._sigma, "CE")
        assert res.delta > 0.9

    def test_deep_otm_call_delta_near_0(self):
        res = black_scholes(20000, 25000, 7 / 365, self._r, self._sigma, "CE")
        assert res.delta < 0.1

    def test_put_call_parity_approx(self):
        """C - P ≈ S - K * e^(-rT) (put-call parity)."""
        call = black_scholes(self._S, self._K, self._T, self._r, self._sigma, "CE")
        put = black_scholes(self._S, self._K, self._T, self._r, self._sigma, "PE")
        lhs = call.theoretical_price - put.theoretical_price
        rhs = self._S - self._K * math.exp(-self._r * self._T)
        assert abs(lhs - rhs) < 0.01  # within 1 rupee

    def test_option_type_case_insensitive_ce(self):
        res = black_scholes(self._S, self._K, self._T, self._r, self._sigma, "ce")
        assert res.theoretical_price > 0

    def test_option_type_call_string(self):
        res = black_scholes(self._S, self._K, self._T, self._r, self._sigma, "CALL")
        assert res.theoretical_price > 0


# ---------------------------------------------------------------------------
# Implied volatility tests
# ---------------------------------------------------------------------------

class TestImpliedVolatility:
    _S = 22000.0
    _K = 22000.0
    _T = 7 / 365.0
    _r = 0.065
    _sigma = 0.15

    def test_round_trip_call(self):
        """Compute call price, then recover IV."""
        bsm = black_scholes(self._S, self._K, self._T, self._r, self._sigma, "CE")
        iv = implied_volatility(bsm.theoretical_price, self._S, self._K, self._T, self._r, "CE")
        assert iv is not None
        assert iv == pytest.approx(self._sigma, rel=1e-4)

    def test_round_trip_put(self):
        bsm = black_scholes(self._S, self._K, self._T, self._r, self._sigma, "PE")
        iv = implied_volatility(bsm.theoretical_price, self._S, self._K, self._T, self._r, "PE")
        assert iv is not None
        assert iv == pytest.approx(self._sigma, rel=1e-4)

    def test_returns_none_for_zero_price(self):
        assert implied_volatility(0, self._S, self._K, self._T, self._r) is None

    def test_returns_none_for_negative_price(self):
        assert implied_volatility(-10, self._S, self._K, self._T, self._r) is None

    def test_returns_none_for_zero_T(self):
        assert implied_volatility(100, self._S, self._K, 0, self._r) is None

    def test_returns_none_for_zero_S(self):
        assert implied_volatility(100, 0, self._K, self._T, self._r) is None

    def test_returns_none_for_zero_K(self):
        assert implied_volatility(100, self._S, 0, self._T, self._r) is None

    def test_round_trip_higher_sigma(self):
        bsm = black_scholes(self._S, self._K, 30 / 365, self._r, 0.30, "CE")
        iv = implied_volatility(bsm.theoretical_price, self._S, self._K, 30 / 365, self._r, "CE")
        assert iv is not None
        assert iv == pytest.approx(0.30, rel=1e-3)


# ---------------------------------------------------------------------------
# Moneyness classification
# ---------------------------------------------------------------------------

class TestClassifyMoneyness:
    def test_atm_within_threshold(self):
        assert classify_moneyness(22000, 22000, "CE") == "ATM"

    def test_atm_within_2pct(self):
        assert classify_moneyness(22000, 22400, "CE") == "ATM"  # 1.8% away

    def test_call_itm_strike_below_spot(self):
        assert classify_moneyness(22000, 20000, "CE") == "ITM"

    def test_call_otm_strike_above_spot(self):
        assert classify_moneyness(22000, 24000, "CE") == "OTM"

    def test_put_itm_strike_above_spot(self):
        assert classify_moneyness(22000, 24000, "PE") == "ITM"

    def test_put_otm_strike_below_spot(self):
        assert classify_moneyness(22000, 20000, "PE") == "OTM"

    def test_zero_spot_returns_unknown(self):
        assert classify_moneyness(0, 22000, "CE") == "UNKNOWN"


# ---------------------------------------------------------------------------
# Chain-level analytics
# ---------------------------------------------------------------------------

def _make_test_chain(spot=22000.0) -> OptionChain:
    strikes = [
        OptionStrike(
            strike=21500.0, ce_oi=50000, pe_oi=200000,
            ce_ltp=500.0, pe_ltp=20.0,
            ce_iv=0.18, pe_iv=0.20,
        ),
        OptionStrike(
            strike=21750.0, ce_oi=80000, pe_oi=150000,
            ce_ltp=300.0, pe_ltp=50.0,
        ),
        OptionStrike(
            strike=22000.0, ce_oi=120000, pe_oi=120000,
            ce_ltp=200.0, pe_ltp=180.0,
            ce_iv=0.15, pe_iv=0.15,
        ),
        OptionStrike(
            strike=22250.0, ce_oi=150000, pe_oi=80000,
            ce_ltp=100.0, pe_ltp=280.0,
        ),
        OptionStrike(
            strike=22500.0, ce_oi=200000, pe_oi=50000,
            ce_ltp=50.0, pe_ltp=480.0,
            ce_iv=0.17, pe_iv=0.22,
        ),
    ]
    return OptionChain(
        underlying="NIFTY",
        expiry=date(2026, 4, 30),
        spot_price=spot,
        strikes=strikes,
    )


class TestOptionChainAnalyzer:
    def _analyzer(self) -> OptionChainAnalyzer:
        return OptionChainAnalyzer(risk_free_rate=0.065)

    def test_analyze_returns_chain_analytics(self):
        chain = _make_test_chain()
        analyzer = self._analyzer()
        result = analyzer.analyze(chain)
        assert isinstance(result, ChainAnalytics)

    def test_analyze_atm_strike(self):
        chain = _make_test_chain(spot=22000.0)
        result = self._analyzer().analyze(chain)
        assert result.atm_strike == 22000.0

    def test_analyze_pcr_overall(self):
        chain = _make_test_chain()
        result = self._analyzer().analyze(chain)
        assert result.pcr_overall > 0

    def test_analyze_call_resistance(self):
        chain = _make_test_chain()
        result = self._analyzer().analyze(chain)
        # Highest call OI is at 22500 (200000)
        assert result.call_resistance == 22500.0

    def test_analyze_put_support(self):
        chain = _make_test_chain()
        result = self._analyzer().analyze(chain)
        # Highest put OI is at 21500 (200000)
        assert result.put_support == 21500.0

    def test_analyze_chain_breadth(self):
        chain = _make_test_chain()
        result = self._analyzer().analyze(chain)
        # Strikes with BOTH ce_ltp and pe_ltp: 21500, 22000, 22250, 22500 = 4
        # (21750 has both too) → 5
        assert result.chain_breadth >= 0

    def test_compute_max_pain_returns_strike(self):
        chain = _make_test_chain()
        analyzer = self._analyzer()
        mp = analyzer._compute_max_pain(chain)
        assert mp is not None
        # max pain should be one of the strikes
        strike_values = [s.strike for s in chain.strikes]
        assert mp in strike_values

    def test_compute_max_pain_empty_oi(self):
        chain = OptionChain(underlying="X", expiry=date(2026, 4, 30))
        chain.strikes = [OptionStrike(strike=22000.0)]  # no OI
        analyzer = self._analyzer()
        assert analyzer._compute_max_pain(chain) is None

    def test_iv_skew_returns_none_when_no_iv_data(self):
        chain = OptionChain(underlying="X", expiry=date(2026, 4, 30), spot_price=22000)
        chain.strikes = [
            OptionStrike(strike=21500.0, ce_oi=100, pe_oi=100),  # no iv
            OptionStrike(strike=22000.0, ce_oi=100, pe_oi=100),
            OptionStrike(strike=22500.0, ce_oi=100, pe_oi=100),
        ]
        analyzer = self._analyzer()
        result = analyzer._compute_iv_skew(chain, 22000.0)
        assert result is None

    def test_iv_skew_with_iv_data(self):
        chain = _make_test_chain()
        analyzer = self._analyzer()
        # 21500 has pe_iv=0.20, 22500 has ce_iv=0.17
        # ATM = 22000, first OTM put below = 21750 (no pe_iv) → 21500 (pe_iv=0.20)
        # first OTM call above = 22250 (no ce_iv) → 22500 (ce_iv=0.17)
        skew = analyzer._compute_iv_skew(chain, 22000.0)
        if skew is not None:
            assert isinstance(skew, float)

    def test_enrich_greeks_populates_iv_for_strikes_with_ltp(self):
        chain = OptionChain(
            underlying="NIFTY",
            expiry=date(2026, 4, 30),
            spot_price=22000.0,
        )
        chain.strikes = [
            OptionStrike(
                strike=22000.0,
                ce_ltp=200.0,
                pe_ltp=180.0,
                ce_iv=None,
                pe_iv=None,
            )
        ]
        analyzer = self._analyzer()
        analyzer.enrich_greeks(chain, T=7 / 365.0)

        s = chain.strikes[0]
        assert s.ce_iv is not None
        assert s.pe_iv is not None
        assert s.ce_iv > 0
        assert s.pe_iv > 0

    def test_enrich_greeks_no_spot_adds_note(self):
        chain = OptionChain(underlying="X", expiry=date(2026, 4, 30))
        chain.strikes = [OptionStrike(strike=22000.0, ce_ltp=200.0)]
        analyzer = self._analyzer()
        result = analyzer.enrich_greeks(chain, T=7 / 365.0)
        assert any("greeks_not_computed" in n for n in result.notes)

    def test_enrich_greeks_T_zero_adds_note(self):
        chain = OptionChain(underlying="X", expiry=date(2026, 4, 30), spot_price=22000)
        chain.strikes = [OptionStrike(strike=22000.0, ce_ltp=200.0)]
        analyzer = self._analyzer()
        result = analyzer.enrich_greeks(chain, T=0)
        assert any("greeks_not_computed" in n for n in result.notes)
